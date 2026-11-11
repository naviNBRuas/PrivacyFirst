"""Privacy report: what was redacted and whether verification passed.

The report contains counts, reasons, and metadata KEY names only. It never
contains faces, crops, embeddings, thumbnails, or metadata values.
"""
from __future__ import annotations
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from . import __version__
from .metadata import MetadataResult
from .pipeline import RedactionPipeline

RESIDUAL_RISK_STATEMENT = (
    "Face replacement and redaction reduce privacy risk but do not by themselves guarantee "
    "anonymization under any law or regulation. People can still be identified from other cues: "
    "voice, body, clothing, tattoos, location, background, text, and surrounding context. "
    "Verification passing means the tested recognizers did not match; it is not proof that "
    "no recognizer, present or future, could."
)

PHASE1_NOTICE = (
    "Faces are redacted by blur/mosaic/block unless the face-change path is enabled with a real replacer. "
    "The only replacer in this build is a non-AI stub. Voice is not anonymized (audio is dropped by default)."
)


def verification_status(p: RedactionPipeline) -> str:
    s = p.stats
    if not s.verifier_enabled:
        return "not_run"
    if s.verifier_unresolved_frames:
        return "failed_frames_blocked"      # output is safe (blocked) but verification did not pass cleanly
    if s.verifier_escalations:
        return "passed_after_escalation"
    return "passed"


def _context_section(p: RedactionPipeline) -> tuple[dict, list[str]]:
    s, c = p.stats, p.context
    cfg = c.cfg
    tracks = s.context_tracks
    red = [t for t in tracks.values() if t["treatment"]]
    flag = [t for t in tracks.values() if not t["treatment"]]
    info = dict(getattr(c, "info", {}) or {})
    d = {**info, "mode": "two_pass" if p.plan_summary else "live", "config": cfg.to_dict(),
         "frames_scanned": s.context_scans, "scan_failures_frames_blocked": s.context_scan_errors,
         "tracks_by_kind": dict(Counter(t["kind"] for t in tracks.values())),
         "tracks_redacted": len(red), "tracks_flagged_only": len(flag),
         "redacted_region_frames": sum(t["redacted_frames"] for t in tracks.values()),
         "flagged_region_frames": sum(t["frames"] - t["redacted_frames"] for t in tracks.values()),
         "backfilled_regions": s.context_backfilled, "review_escalations_applied": s.escalations_applied,
         "plan": getattr(getattr(c, "plan", None), "summary", None), "recognised_text_stored": False}
    w = ["Context scan is heuristic OCR (v0): text that is small, blurred, rotated, stylised, upside down or not in the installed OCR "
         "languages is NOT found, and name tags, uniforms, logos and tattoos are never scanned."]
    if cfg.scan_every > 1:
        w.append(f"Context scan ran on every {cfg.scan_every}th frame: an item visible for fewer frames between scans can be missed.")
    if flag:
        w.append(f"{len(flag)} text or plate-shaped region(s) were flagged but NOT redacted; review them before publishing.")
    if s.context_scan_errors:
        w.append(f"{s.context_scan_errors} frame(s) failed the context scan and were fully blocked.")
    return d, w


@dataclass
class PrivacyReport:
    data: dict = field(default_factory=dict)

    @classmethod
    def build(cls, p: RedactionPipeline, source_name: str, metadata: Optional[MetadataResult] = None,
              minor_exception_used: bool = False) -> "PrivacyReport":
        s = p.stats
        tracks = []
        for tid, t in sorted(s.tracks.items()):
            tracks.append({"track_id": tid, "first_frame": t["first_frame"], "last_frame": t["last_frame"],
                           "frames_redacted": t["frames"], "ghost_frames": t["ghost_frames"],
                           "treatments": {k: v for k, v in t["treatments"].items() if v},
                           "treated_as_minor_risk": t["minor_risk"],
                           "synthetic_identity_id": t.get("identity_id"),
                           "swap_demotions": dict(t.get("demotions", {}))})
        warnings = []
        if "placeholder" in p.detector.name:
            warnings.append("Placeholder detector in use: NOT suitable for real privacy claims.")
        vname = p.verifier.name if p.verifier is not None else None
        if vname and ("placeholder" in vname or vname == "scripted"):
            warnings.append(f"Verifier '{vname}' is a placeholder/scripted stand-in: a 'passed' result is NOT meaningful.")
        if s.swap_enabled:
            if s.replacer_is_stub:
                warnings.append("Stub replacer in use: the output is a cartoon stand-in, NOT an AI face change.")
            if s.unvetted_identities:
                warnings.append("Unvetted identity library in use: identities have not passed offline vetting.")
            if not s.recognizers:
                warnings.append("No recognizer-ensemble verification configured: minor-risk people never receive a swap; "
                                "adult swaps are unverified.")
            if s.replacer_errors:
                warnings.append(f"{s.replacer_errors} replacer error(s) occurred; affected people fell back to mosaic.")
        if not p.plan_summary:
            warnings.append("Live mode: a face first detected more than the lookahead after it appeared can leave earlier frames "
                            "unredacted (use two-pass mode for recorded files).")
        ctx = None
        if s.context_enabled:
            ctx, cw = _context_section(p)
            warnings += cw
        if s.detector_errors:
            warnings.append(f"{s.detector_errors} frame(s) had detector errors and were fully blocked.")
        if s.verifier_unresolved_frames:
            warnings.append(f"{s.verifier_unresolved_frames} frame(s) failed verification and were blocked.")
        if metadata and not metadata.ok:
            warnings.append("Metadata verification FAILED; do not publish this file.")
        if metadata and not metadata.audio_dropped:
            warnings.append("Audio retained; voice is not anonymized.")
        d = {
            "report_version": 1,
            "tool_version": __version__,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source_name,
            "detector": p.detector.name,
            "policy": p.engine.cfg.to_dict(),
            "lookahead_frames": p.lookahead,
            "mode": "two_pass" if p.plan_summary else "live",
            "two_pass": p.plan_summary,
            "frames": {"in": s.frames_in, "out": s.frames_out},
            "tracks": tracks,
            "fallback_reasons": dict(s.reasons),
            "scene_level_events": dict(s.scene_events),
            "backfilled_regions": s.backfilled_regions,
            "minor_exception_used": minor_exception_used,
            "verification": {
                "status": verification_status(p),
                "verifier": vname,
                "frames_scanned": s.verifier_frames,
                "frames_with_residual_faces": s.verifier_residual_frames,
                "escalations": s.verifier_escalations,
                "unresolved_frames_blocked": s.verifier_unresolved_frames,
            },
            "metadata": None if metadata is None else {
                "verified_clean": metadata.ok,
                "keys_removed": sorted(set(metadata.keys_before) - set(metadata.keys_after)),
                "keys_remaining": metadata.keys_after,
                "gps_present_before": metadata.has_gps_before,
                "gps_present_after": metadata.has_gps_after,
                "audio_dropped": metadata.audio_dropped,
            },
            "swap": None if not s.swap_enabled else {
                "replacer": s.replacer_name,
                "replacer_is_stub": s.replacer_is_stub,
                "region_frames_swapped": s.swap_frames,
                "swaps_demoted_at_render": s.render_demotions,
                "demotions_by_reason": dict(s.swap_demotions),
                "identity_assignments": s.identity_assignments,
                "unvetted_identities_in_use": s.unvetted_identities,
                "replacer_errors": s.replacer_errors,
                "recognizer_verification": {"recognizers": s.recognizers, "thresholds": s.verif_thresholds,
                                            "checks": s.verif_checks, "failures": s.verif_failures},
            },
            "context_identifier_scan": "run_v0_heuristic" if ctx else "not_run",
            "context": ctx,
            "warnings": warnings,
            "notice": PHASE1_NOTICE,
            "residual_risk_statement": RESIDUAL_RISK_STATEMENT,
        }
        return cls(d)

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2)

    def to_markdown(self) -> str:
        d = self.data
        v = d["verification"]
        lines = [f"# Privacy Report: {d['source']}", "",
                 f"- Generated: {d['generated_utc']}  |  Tool v{d['tool_version']}",
                 f"- Detector: {d['detector']}",
                 f"- Frames: {d['frames']['in']} in / {d['frames']['out']} out",
                 f"- Faces/tracks redacted: {len(d['tracks'])}",
                 f"- Verification: **{v['status']}** ({v['frames_scanned']} frames scanned, "
                 f"{v['escalations']} escalations, {v['unresolved_frames_blocked']} unresolved/blocked)",
                 f"- Minor exception used: {d['minor_exception_used']}", ""]
        if d["warnings"]:
            lines += ["## Warnings", *[f"- {w}" for w in d["warnings"]], ""]
        lines += [f"- Verifier: {v.get('verifier')}", ""] if v.get("verifier") else []
        lines += ["## Tracks", "", "| Track | Frames | Ghost | Treatments | Minor-risk |", "|---|---|---|---|---|"]
        for t in d["tracks"]:
            lines.append(f"| {t['track_id']} | {t['first_frame']}-{t['last_frame']} ({t['frames_redacted']}) | "
                         f"{t['ghost_frames']} | {t['treatments']} | {t['treated_as_minor_risk']} |")
        lines += ["", "## Fallback reasons", "", *[f"- {k}: {n}" for k, n in sorted(d["fallback_reasons"].items())], ""]
        if d["scene_level_events"]:
            lines += ["## Scene-level events", *[f"- {k}: {n}" for k, n in d["scene_level_events"].items()], ""]
        tp = d.get("two_pass")
        if tp:
            lines += ["## Two-pass analysis (geometry only, no pixels kept)",
                      f"- Tracklets {tp['tracklets']} merged into {tp['persons']} people ({tp['stitched_links']} stitches)",
                      f"- Frames covered before first detection: {tp['back_extended_frames']} | interpolated gap frames: "
                      f"{tp['interpolated_gap_frames']} | trailing ghost frames: {tp['trailing_ghost_frames']}", ""]
        sw = d.get("swap")
        if sw:
            rv = sw["recognizer_verification"]
            lines += ["## Face change (swap)", f"- Replacer: {sw['replacer']} (stub: {sw['replacer_is_stub']})",
                      f"- Region-frames swapped: {sw['region_frames_swapped']} | demoted at render: {sw['swaps_demoted_at_render']}",
                      f"- Demotions by reason: {sw['demotions_by_reason'] or 'none'}",
                      f"- Identity assignments: {sw['identity_assignments']} (unvetted library: {sw['unvetted_identities_in_use']})",
                      f"- Recognizer check: {rv['checks']} checks, {rv['failures']} failures; recognizers: "
                      f"{', '.join(rv['recognizers']) or 'none'}", ""]
        m = d["metadata"]
        if m:
            lines += ["## Metadata", f"- Verified clean: **{m['verified_clean']}**",
                      f"- GPS before/after: {m['gps_present_before']} / {m['gps_present_after']}",
                      f"- Tag keys removed: {', '.join(m['keys_removed']) or 'none'}",
                      f"- Audio dropped: {m['audio_dropped']}", ""]
        c = d.get("context")
        if c:
            lines += ["## Context identifiers (scan v0, heuristic OCR; recognised text is never stored)",
                      f"- Engine: {c.get('ocr_engine')} (languages: {c.get('ocr_languages')}), scan every {c['config']['scan_every']} frame(s), "
                      f"{c['mode']} mode",
                      f"- Frames scanned: {c['frames_scanned']} | scan failures (frames blocked): {c['scan_failures_frames_blocked']}",
                      f"- Regions by kind: {c['tracks_by_kind'] or 'none'}",
                      f"- Redacted: {c['tracks_redacted']} region(s), {c['redacted_region_frames']} region-frames | "
                      f"flagged only (pixels untouched, needs review): {c['tracks_flagged_only']} region(s), {c['flagged_region_frames']} region-frames",
                      f"- Reviewer escalations applied: {c['review_escalations_applied']}", ""]
        scan_line = ("scan v0 ran (heuristic OCR; see warnings). Name tags, uniforms, logos and tattoos are never scanned"
                     if c else "not run (off by default; enable with --context-scan)")
        lines += ["## Not covered", f"- Context identifiers (plates, name tags, addresses, tattoos): {scan_line}",
                  "", "## Notice", d["notice"], "", "## Residual risk", d["residual_risk_statement"], ""]
        return "\n".join(lines)
