"""Deterministic policy engine: (track state, scene state) -> treatment.

Kept separate from all ML on purpose so it is auditable and unit-testable.
Rules only ever *escalate* treatment (BLUR < MOSAIC < BLOCK); nothing here can
downgrade a face to unredacted.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import numpy as np
from .tracking import Track
from .types import Decision, Treatment, stronger


@dataclass
class SwapContext:
    """Per-track, per-frame facts the swap gate needs. Built by the pipeline, consumed by the policy."""
    health: Optional[float] = None       # None = replacement was not evaluated this frame
    budget_ok: bool = True
    identity_ok: bool = True
    demoted: bool = False                # sticky or permanent demotion active
    verified: Optional[bool] = None      # latest recognizer-ensemble result; None = never checked
    minor_gate_ok: bool = False          # identity is child_ok and the minor path is enabled
    replacer_error: bool = False


STICKY_REASONS = {"replacer_unhealthy", "replacer_error", "verification_failed", "low_confidence", "ghost_track"}
# Demotions caused by a detection dropout (not by anything the replacer or recognizers did) use the shorter hysteresis.
DROPOUT_REASONS = {"low_confidence", "ghost_track"}


@dataclass
class PolicyConfig:
    conf_threshold: float = 0.5          # below this, a live detection is "low confidence"
    default_treatment: Treatment = Treatment.BLUR
    low_conf_treatment: Treatment = Treatment.MOSAIC
    ghost_treatment: Treatment = Treatment.MOSAIC
    minor_treatment: Treatment = Treatment.MOSAIC
    minor_prob_threshold: float = 0.2    # deliberately low: over-flag minors
    unknown_age_is_minor: bool = True    # no age model in Phase 1, so this is the strict default
    dark_luma: float = 12.0              # mean luma (0-255) below which "no faces found" is untrustworthy
    scene_dark_treatment: Treatment = Treatment.MOSAIC
    scene_error_treatment: Treatment = Treatment.BLOCK
    region_margin: float = 0.4           # expand face box to cover the head (hair, ears, jaw)
    # --- AI face change (SWAP) gates. Off by default: nothing swaps unless enabled AND every gate passes.
    swap_enabled: bool = False
    swap_min_conf: float = 0.70
    swap_min_track_hits: int = 5         # track must be stable before a swap is shown
    swap_min_health: float = 0.60        # replacer self-assessment
    swap_demote_treatment: Treatment = Treatment.MOSAIC
    swap_sticky_frames: int = 30         # hysteresis after a replacer/recognizer problem, so output does not flip-flop
    swap_sticky_dropout_frames: int = 15 # hysteresis after a detection dropout (ghost / low confidence); run 004 sweep, provisional
    minor_swap_allowed: bool = True      # photoreal change for minor-risk tracks, behind the stricter gate (ADR 0004)
    swap_dropout_release_streak: int = -1  # lift a dropout demotion after this many consecutive detections. -1 = mode default
                                           # (off in live mode, 3 in two-pass: run 005 sweep), 0 = explicitly never early
    swap_interp_max_gap: int = 4         # two-pass only: a gap this short, bracketed by detections on BOTH sides, may still swap

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (v.value if isinstance(v, Treatment) else v) for k, v in d.items()}

    @classmethod
    def strict(cls) -> "PolicyConfig":
        return cls()

    @classmethod
    def standard(cls) -> "PolicyConfig":
        """Known-adult footage: unknown age is NOT escalated. Not the default."""
        return cls(unknown_age_is_minor=False)


class PolicyEngine:
    def __init__(self, cfg: Optional[PolicyConfig] = None):
        self.cfg = cfg or PolicyConfig.strict()

    def is_minor_risk(self, track: Track) -> bool:
        if track.minor_prob is None:
            return self.cfg.unknown_age_is_minor
        return track.minor_prob >= self.cfg.minor_prob_threshold

    def position_supported(self, track: Track) -> bool:
        """Is the track's box backed by a detection, or (two-pass only) interpolated between two close detections?"""
        if not track.is_ghost:
            return True
        return track.interp_ok and 0 < track.gap_len <= self.cfg.swap_interp_max_gap

    def _swap_failures(self, track: Track, ctx: SwapContext) -> list[str]:
        c, f = self.cfg, []
        if not self.position_supported(track):
            f.append("ghost_track")
        elif track.conf < c.swap_min_conf:
            f.append("low_confidence")
        if track.hits < c.swap_min_track_hits:
            f.append("track_not_stable")
        if not ctx.identity_ok:
            f.append("no_identity")
        if ctx.demoted:
            f.append("sticky_demotion")
        if ctx.replacer_error:
            f.append("replacer_error")
        elif ctx.health is not None and ctx.health < c.swap_min_health:
            f.append("replacer_unhealthy")
        if ctx.verified is False:
            f.append("verification_failed")
        if self.is_minor_risk(track) and not (c.minor_swap_allowed and ctx.minor_gate_ok and ctx.verified is True):
            f.append("minor_gate_not_passed")        # minors/unknown age need an explicit PASS, not "not checked"
        if not ctx.budget_ok:
            f.append("over_budget")
        if not f and ctx.health is None:
            f.append("replacer_unhealthy")           # never evaluated: do not swap on faith
        return f

    def decide(self, track: Track, swap: Optional[SwapContext] = None) -> Decision:
        c = self.cfg
        t, reasons = c.default_treatment, ["face_detected"]
        if self.is_minor_risk(track):
            t = stronger(t, c.minor_treatment)
            reasons.append("minor_or_unknown_age" if track.minor_prob is None else "minor_likely")
        if track.is_ghost:
            t = stronger(t, c.ghost_treatment)
            reasons.append("ghost_track")
        elif track.conf < c.conf_threshold:
            t = stronger(t, c.low_conf_treatment)
            reasons.append("low_confidence")
        if c.swap_enabled and swap is not None:
            why = self._swap_failures(track, swap)
            if not why:
                return Decision(Treatment.SWAP, ["face_detected", "swap_gate_passed"])
            reasons += [f"swap_gate:{w}" for w in why]
            if why != ["over_budget"]:                # budget overrun demotes to the base treatment, not to mosaic
                t = stronger(t, c.swap_demote_treatment)
        return Decision(t, reasons)

    def scene_decision(self, frame: np.ndarray, detector_ok: bool) -> Optional[Decision]:
        """Frame-level fail-closed checks. Returns None when the frame is trustworthy."""
        if not detector_ok:
            return Decision(self.cfg.scene_error_treatment, ["detector_error"])
        if float(frame.mean()) < self.cfg.dark_luma:
            return Decision(self.cfg.scene_dark_treatment, ["scene_too_dark_to_trust_detection"])
        return None
