"""Streaming pipeline with a lookahead buffer.

Raw frames live only in this in-memory ring buffer. Output is delayed by `lookahead` frames so that
(a) late detections can be backfilled into frames not yet emitted, (b) a swap demotion discovered later
can still be applied to buffered frames, and (c) the residual-face verifier can inspect the rendered
frame before it leaves the pipeline.

Face change (SWAP): only when policy.swap_enabled AND a replacer + identity assigner are supplied. Every
swap must pass the policy gates (see policy.py). Anything else falls back to blur/mosaic/block.
"""
from __future__ import annotations
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from .blend import composite
from .context import ContextFrame, ContextRegion
from .detect import Detector
from .fallback import apply_full_frame, apply_treatment
from .identity import IdentityAssigner, tone_bin_of
from .policy import DROPOUT_REASONS, STICKY_REASONS, PolicyConfig, PolicyEngine, SwapContext
from .replace import FaceReplacer, Replacement
from .swapgate import SwapState, SwapVerifier
from .tracking import Tracker
from .types import STRENGTH, Box, Decision, Treatment, stronger

STRENGTH_OF = {t.value: v for t, v in STRENGTH.items()}


@dataclass
class Region:
    track_id: int
    box: Box
    treatment: Treatment
    reasons: list[str]
    swap: Optional[Replacement] = None
    identity_id: Optional[str] = None


@dataclass
class BufferedFrame:
    idx: int
    frame: np.ndarray
    regions: dict[int, Region] = field(default_factory=dict)
    scene: Optional[tuple[Treatment, list[str]]] = None
    context: dict[int, ContextRegion] = field(default_factory=dict)   # context-identifier regions (own id namespace)
    context_error: bool = False                                        # the context scan failed on this frame: block it


@dataclass
class OutputFrame:
    idx: int
    frame: np.ndarray
    treatments: dict[int, str]           # track_id -> treatment applied
    notes: list[str]
    # Exact geometry applied, for benchmarking/audit: (track_id, box, treatment). track_id -1 = verifier escalation.
    regions: list = field(default_factory=list)
    scene_treatment: Optional[str] = None    # whole-frame treatment from a scene-level rule, if any
    full_frame_block: bool = False           # verifier blocked the entire frame
    context_regions: list = field(default_factory=list)   # (context id, box, treatment value or None for flag-only, kind value)
    context_error: bool = False              # whole frame blocked because the context scan failed


class PipelineStats:
    def __init__(self) -> None:
        self.frames_in = 0
        self.frames_out = 0
        self.tracks: dict[int, dict] = {}
        self.reasons: Counter = Counter()
        self.scene_events: Counter = Counter()
        self.backfilled_regions = 0
        self.detector_errors = 0
        self.verifier_enabled = False
        self.verifier_frames = 0
        self.verifier_residual_frames = 0
        self.verifier_escalations = 0
        self.verifier_unresolved_frames = 0
        # context-identifier scan (run 006)
        self.context_enabled = False
        self.context_name: Optional[str] = None
        self.context_scans = 0
        self.context_scan_errors = 0
        self.context_tracks: dict[int, dict] = {}
        self.context_backfilled = 0
        self.escalations_applied = 0
        # risk events for the review model: (frame, kind, ref_type, ref_id, treatment or None)
        self.events: list[tuple] = []
        # swap / face change
        self.swap_enabled = False
        self.replacer_name: Optional[str] = None
        self.replacer_is_stub = False
        self.swap_frames = 0                 # region-frames shown as swap in emitted output
        self.render_demotions = 0            # swaps demoted at render time (late verification failure)
        self.swap_demotions: Counter = Counter()
        self.identity_assignments = 0
        self.unvetted_identities = False
        self.verif_checks = 0
        self.verif_failures = 0
        self.replacer_errors = 0
        self.recognizers: list[str] = []
        self.verif_thresholds: dict = {}

    def track(self, tid: int, idx: int) -> dict:
        t = self.tracks.setdefault(tid, {"first_frame": idx, "last_frame": idx, "frames": 0,
                                         "treatments": Counter(), "ghost_frames": 0, "minor_risk": False,
                                         "identity_id": None, "demotions": Counter()})
        t["last_frame"] = idx
        return t


class RedactionPipeline:
    def __init__(self, detector: Detector, policy: Optional[PolicyConfig] = None,
                 lookahead: int = 4, verifier: Optional[Detector] = None,
                 verifier_conf: float = 0.3, tracker: Optional[Tracker] = None,
                 replacer: Optional[FaceReplacer] = None, identities: Optional[IdentityAssigner] = None,
                 swap_verifier: Optional[SwapVerifier] = None, max_swaps: Optional[int] = None,
                 verify_every: int = 5, context=None, face_escalations: Optional[dict] = None,
                 context_escalations: Optional[dict] = None):
        self.detector = detector
        self.engine = PolicyEngine(policy)
        self.tracker = tracker or Tracker()
        self.lookahead = max(1, lookahead)
        self.verifier = verifier
        self.verifier_conf = verifier_conf
        self.buf: deque[BufferedFrame] = deque()
        self.stats = PipelineStats()
        self.stats.verifier_enabled = verifier is not None
        self.context = context                       # ContextSource (LiveContext / PlannedContext) or None
        self.face_esc = dict(face_escalations or {})     # review overrides: escalate-only, never SWAP
        self.context_esc = dict(context_escalations or {})
        for t in list(self.face_esc.values()) + list(self.context_esc.values()):
            if t == Treatment.SWAP:
                raise ValueError("review escalations must be blur/mosaic/block; SWAP is not an escalation")
        if context is not None:
            self.stats.context_enabled, self.stats.context_name = True, getattr(context, "name", "context")
        self.plan_summary: Optional[dict] = None     # set by TwoPassRunner; None in live mode
        self._idx = -1
        # --- swap wiring
        self.replacer, self.identities, self.swap_verifier = replacer, identities, swap_verifier
        self.max_swaps, self.verify_every = max_swaps, max(1, verify_every)
        self.swap_on = bool(self.engine.cfg.swap_enabled)
        if self.swap_on and (replacer is None or identities is None):
            raise ValueError("policy.swap_enabled requires a replacer and an identity assigner")
        self.swap_state: dict[int, SwapState] = {}
        self.stats.swap_enabled = self.swap_on
        if self.swap_on:
            self.stats.replacer_name = replacer.name
            self.stats.replacer_is_stub = bool(getattr(replacer, "is_stub", False))
            self.stats.unvetted_identities = identities.uses_unvetted
        if swap_verifier is not None:
            self.stats.recognizers = swap_verifier.names
            self.stats.verif_thresholds = {"adult": swap_verifier.max_sim_adult, "minor": swap_verifier.max_sim_minor}

    # ---- ingest -----------------------------------------------------------
    def push(self, frame: np.ndarray) -> list[OutputFrame]:
        self._idx += 1
        self.stats.frames_in += 1
        h, w = frame.shape[:2]
        entry = BufferedFrame(self._idx, frame.copy())
        try:
            dets = list(self.detector.detect(frame))
            ok = True
        except Exception:                       # any detector failure fails closed
            dets, ok = [], False
            self.stats.detector_errors += 1
        scene = self.engine.scene_decision(frame, ok)
        if scene:
            entry.scene = (scene.treatment, scene.reasons)
            for r in scene.reasons:
                self.stats.scene_events[r] += 1
        tracks = self.tracker.update(dets, w, h) if ok else self.tracker.update([], w, h)
        budget = self._budget(tracks) if self.swap_on else {}
        if self.swap_on:
            live = {t.id for t in tracks}
            for tid in [k for k in self.swap_state if k not in live and self.swap_state[k].identity is not None]:
                self.identities.release(tid)                   # free the identity for reuse by later tracks
                self.swap_state[tid].identity = None
        for t in tracks:
            sctx = repl = st = None
            if self.swap_on:
                st = self.swap_state.setdefault(t.id, SwapState())
                sctx, repl = self._swap_context(frame, t, st, w, h, budget.get(t.id, True))
            d = self.engine.decide(t, sctx)
            if d.treatment == Treatment.SWAP and repl is None:
                d = Decision(Treatment.BLOCK, d.reasons + ["swap_without_replacement"])    # cannot happen; fail closed
            esc = self.face_esc.get(t.id)
            if esc is not None and stronger(d.treatment, esc) != d.treatment:             # reviewer escalation: escalate-only
                d = Decision(stronger(d.treatment, esc), d.reasons + ["review_escalation"])
                self.stats.escalations_applied += 1
            if st is not None:
                self._after_decision(t.id, st, d)
            region = Region(t.id, t.box.expanded(self.engine.cfg.region_margin, w, h), d.treatment, d.reasons,
                            repl if d.treatment == Treatment.SWAP else None,
                            st.identity.id if (st is not None and st.identity) else None)
            entry.regions[t.id] = region
            ts = self.stats.track(t.id, self._idx)
            ts["frames"] += 1
            ts["treatments"][d.treatment.value] += 1
            ts["ghost_frames"] += int(t.is_ghost)
            ts["minor_risk"] = ts["minor_risk"] or self.engine.is_minor_risk(t)
            if region.identity_id:
                ts["identity_id"] = region.identity_id
            for r in d.reasons:
                self.stats.reasons[r] += 1
            # Backfill: a track born right now was visible in earlier buffered frames too.
            if t.born_frame == self._idx and not t.is_ghost:
                self._backfill(t, stronger(d.treatment, Treatment.BLUR) if d.treatment != Treatment.SWAP else
                               self.engine.cfg.swap_demote_treatment, d.reasons, w, h)
        if self.context is not None:
            self._ingest_context(entry)
        self.buf.append(entry)
        out: list[OutputFrame] = []
        while len(self.buf) > self.lookahead:
            out.append(self._emit(self.buf.popleft()))
        return out

    def flush(self) -> list[OutputFrame]:
        out = []
        while self.buf:
            out.append(self._emit(self.buf.popleft()))
        return out

    # ---- context identifiers ------------------------------------------------
    def _ingest_context(self, entry: BufferedFrame) -> None:
        try:
            cf = self.context.frame(entry.idx, entry.frame)
        except Exception:                                  # any failure of the context source fails closed
            cf = ContextFrame(error=True, scanned=True)
        entry.context_error = cf.error
        if cf.scanned:
            self.stats.context_scans += 1
        if cf.error:
            self.stats.context_scan_errors += 1
        for cr in cf.regions:
            tr = cr.treatment
            esc = self.context_esc.get(cr.cid)
            if esc is not None and (tr is None or stronger(tr, esc) != tr):
                tr = esc if tr is None else stronger(tr, esc)
                self.stats.escalations_applied += 1
            entry.context[cr.cid] = ContextRegion(cr.cid, cr.kind, cr.box, tr, cr.held)
        for cid in cf.new_ids:                             # a track born now was already there in the buffered frames
            src = entry.context.get(cid)
            if src is None:
                continue
            for e in self.buf:
                if cid not in e.context:
                    e.context[cid] = ContextRegion(cid, src.kind, src.box, src.treatment, True)
                    self.stats.context_backfilled += 1

    # ---- swap helpers -----------------------------------------------------
    def _budget(self, tracks) -> dict[int, bool]:
        if self.max_swaps is None:
            return {}
        live = sorted((t for t in tracks if not t.is_ghost), key=lambda t: t.box.area, reverse=True)
        return {t.id: i < self.max_swaps for i, t in enumerate(live)}      # largest faces keep priority

    def _swap_context(self, frame, t, st: SwapState, w, h, budget_ok: bool):
        cfg = self.engine.cfg
        if st.identity is None and not st.identity_tried:
            st.identity_tried = True
            age = "unknown" if t.minor_prob is None else ("child" if t.minor_prob >= cfg.minor_prob_threshold else "adult")
            st.identity = self.identities.assign(t.id, tone_bin_of(frame, t.box), age)    # coarse bins only
            if st.identity:
                self.stats.identity_assignments += 1
        ident = st.identity
        if cfg.swap_dropout_release_streak > 0 and t.streak >= cfg.swap_dropout_release_streak:
            st.dropout_until = -1
        ctx = SwapContext(budget_ok=budget_ok, identity_ok=ident is not None, demoted=st.is_demoted(self._idx),
                          verified=st.verified,
                          minor_gate_ok=bool(ident and ident.child_ok and cfg.minor_swap_allowed))
        eligible = (ident is not None and self.engine.position_supported(t) and t.conf >= cfg.swap_min_conf
                    and t.hits >= cfg.swap_min_track_hits and not ctx.demoted and budget_ok)
        if not eligible:
            return ctx, None
        sm = [f(v) for f, v in zip(st.filters, (t.box.x1, t.box.y1, t.box.x2, t.box.y2))]    # One-Euro geometry smoothing
        head = Box(*sm).expanded(cfg.region_margin, w, h)
        try:
            repl = self.replacer.replace(frame, t, head, ident, self._idx)
        except Exception:
            self.stats.replacer_errors += 1
            ctx.replacer_error = True
            return ctx, None
        repl.patch = st.stab.update(repl.patch)                                               # temporal patch smoothing
        ctx.health = repl.health
        minor = self.engine.is_minor_risk(t)
        if self.swap_verifier is not None and (st.verified is None or self._idx - st.last_verified >= self.verify_every):
            x1, y1, x2, y2 = repl.head_box.clamp_int(w, h)
            res = self.swap_verifier.check(frame[y1:y2, x1:x2], repl.patch, strict=minor)
            st.verified, st.last_verified = res.ok, self._idx
            self.stats.verif_checks += 1
            if not res.ok:
                st.perm_demoted = True                                                       # a failed check demotes the track for good
                self.stats.verif_failures += 1
            ctx.verified, ctx.demoted = st.verified, st.is_demoted(self._idx)
        return ctx, repl

    def _after_decision(self, tid: int, st: SwapState, d: Decision) -> None:
        if d.treatment == Treatment.SWAP:
            return
        why = [r.split(":", 1)[1] for r in d.reasons if r.startswith("swap_gate:")]
        for r in why:
            self.stats.swap_demotions[r] += 1
            st.demotions[r] += 1
        cfg = self.engine.cfg
        for r in why:
            if r in STICKY_REASONS:
                if r in DROPOUT_REASONS:
                    st.dropout_until = max(st.dropout_until, self._idx + cfg.swap_sticky_dropout_frames)
                else:
                    st.demoted_until = max(st.demoted_until, self._idx + cfg.swap_sticky_frames)

    def _backfill(self, t, treatment, reasons, w, h) -> None:
        for k, e in enumerate(reversed(self.buf), start=1):   # k frames before now
            if t.id in e.regions:
                continue
            # Extrapolate backwards and widen: older frames carry more position uncertainty.
            box = t.box.shifted(-t.vel[0] * k, -t.vel[1] * k)
            box = box.expanded(self.engine.cfg.region_margin + 0.1 * k, w, h)
            e.regions[t.id] = Region(t.id, box, stronger(treatment, Treatment.BLUR), reasons + ["backfill"])
            self.stats.backfilled_regions += 1
            self.stats.reasons["backfill"] += 1
            st = self.stats.track(t.id, e.idx)
            st["first_frame"] = min(st["first_frame"], e.idx)

    # ---- render + verify --------------------------------------------------
    def _render(self, e: BufferedFrame):
        out = e.frame.copy()
        applied: dict[int, str] = {}
        boxes: dict[int, Box] = {}
        cfg = self.engine.cfg
        if e.scene:
            apply_full_frame(out, e.scene[0])
        for tid, r in e.regions.items():
            if r.treatment == Treatment.SWAP:
                st = self.swap_state.get(tid)
                if r.swap is None or (st is not None and st.perm_demoted):
                    # Late demotion (e.g. verification failed after this frame was buffered): re-check at render.
                    apply_treatment(out, r.box, cfg.swap_demote_treatment)
                    applied[tid], boxes[tid] = cfg.swap_demote_treatment.value, r.box
                    self.stats.render_demotions += 1
                    ts = self.stats.tracks.get(tid)
                    if ts:
                        ts["treatments"]["swap"] -= 1
                        ts["treatments"][cfg.swap_demote_treatment.value] += 1
                    continue
                composite(out, r.swap.head_box, r.swap.patch, r.swap.mask, e.frame,
                          np.random.default_rng(e.idx * 1000003 + tid))
                applied[tid], boxes[tid] = "swap", r.swap.head_box
                self.stats.swap_frames += 1
            else:
                apply_treatment(out, r.box, r.treatment)
                applied[tid], boxes[tid] = r.treatment.value, r.box
        # Context regions go LAST: they destroy pixels, so they can never be undone by a face swap pasted over them.
        if e.context_error:
            apply_full_frame(out, Treatment.BLOCK)
        for cr in e.context.values():
            if cr.treatment is not None:
                apply_treatment(out, cr.box, cr.treatment)
        return out, applied, boxes

    def _emit(self, e: BufferedFrame) -> OutputFrame:
        out, applied, boxes = self._render(e)
        notes: list[str] = []
        extra_boxes: list[Box] = []
        full = False
        if self.verifier is not None:
            ignore = [boxes[t] for t, a in applied.items() if a == "swap"]
            out, extra, extra_boxes, full = self._verify(out, ignore)
            notes += extra
        self.stats.frames_out += 1
        regions = [(tid, boxes[tid], applied[tid]) for tid in applied]
        regions += [(-1, b, Treatment.BLOCK.value) for b in extra_boxes]
        ctx = [(c.cid, c.box, c.treatment.value if c.treatment is not None else None, c.kind.value) for c in e.context.values()]
        self._record(e, notes, ctx)
        return OutputFrame(e.idx, out, applied, notes, regions, e.scene[0].value if e.scene else None, full, ctx, e.context_error)

    def _record(self, e: BufferedFrame, notes: list[str], ctx: list) -> None:
        """Risk events for the review model, recorded on FINAL frames (after backfill and render-time demotion)."""
        ev, s = self.stats.events, self.stats
        for tid, r in e.regions.items():
            for k in ("low_confidence", "ghost_track"):
                if k in r.reasons:
                    ev.append((e.idx, k, "face", tid, r.treatment.value))
        if e.scene:
            ev.append((e.idx, "scene_block", "frame", -1, e.scene[0].value))
        for n in notes:
            ev.append((e.idx, "verifier_escalation", "frame", -1, Treatment.BLOCK.value))
        if e.context_error:
            ev.append((e.idx, "context_scan_error", "frame", -1, Treatment.BLOCK.value))
        for cid, _, tr, kind in ctx:
            ev.append((e.idx, "context_redacted" if tr else "context_flagged", "context", cid, tr))
            t = s.context_tracks.setdefault(cid, {"kind": kind, "first": e.idx, "last": e.idx, "frames": 0, "treatment": None, "redacted_frames": 0})
            t["last"], t["frames"] = e.idx, t["frames"] + 1
            t["redacted_frames"] += int(tr is not None)
            if tr and (t["treatment"] is None or STRENGTH_OF[tr] > STRENGTH_OF[t["treatment"]]):
                t["treatment"] = tr

    def _verify(self, out: np.ndarray, ignore: list[Box]):
        """Residual-face scan. Detections inside a SWAPPED head box are expected (the synthetic face) and
        are judged by the recognizer gate instead, so they are not escalated here."""
        s = self.stats
        s.verifier_frames += 1
        notes: list[str] = []
        boxes: list[Box] = []
        inside = lambda d: any(b.x1 <= d.box.center[0] <= b.x2 and b.y1 <= d.box.center[1] <= b.y2 for b in ignore)
        try:
            res = [d for d in self.verifier.detect(out) if d.conf >= self.verifier_conf and not inside(d)]
        except Exception:
            apply_full_frame(out, Treatment.BLOCK)           # verifier failure: block the frame
            s.verifier_unresolved_frames += 1
            return out, ["verifier_error_frame_blocked"], [], True
        if not res:
            return out, notes, boxes, False
        s.verifier_residual_frames += 1
        h, w = out.shape[:2]
        for d in res:                                         # escalate: solid-fill any residual face
            eb = d.box.expanded(0.3, w, h)
            apply_treatment(out, eb, Treatment.BLOCK)
            boxes.append(eb)
            s.verifier_escalations += 1
        notes.append("verifier_escalated")
        again = [d for d in self.verifier.detect(out) if d.conf >= self.verifier_conf and not inside(d)]
        if again:                                             # still visible: block the whole frame
            apply_full_frame(out, Treatment.BLOCK)
            s.verifier_unresolved_frames += 1
            notes.append("verifier_full_frame_block")
            return out, notes, boxes, True
        return out, notes, boxes, False
