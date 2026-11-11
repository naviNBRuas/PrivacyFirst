"""Two-pass recorded mode (run 004)."""
import numpy as np
import pytest
from conftest import det, make_frame, region_std, W, H
from privacyfirst.detect import ScriptedDetector
from privacyfirst.identity import IdentityAssigner, generate_stub_library
from privacyfirst.offline import (OfflineConfig, PlanMismatchError, TwoPassRunner, analyze)
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.policy import PolicyConfig
from privacyfirst.replace import StubReplacer
from privacyfirst.report import PrivacyReport
from privacyfirst.swapgate import FunctionRecognizer, SwapVerifier
from privacyfirst.types import Box, Detection

FACE = Box(60, 40, 100, 80)


def frames_of(n, face=FACE):
    return [make_frame(i, face) for i in range(n)]


def two_pass(script, n, face=FACE, policy=None, cfg=None, **kw):
    fr = frames_of(n, face)
    r = TwoPassRunner(lambda: iter(fr), ScriptedDetector(script), policy, cfg, **kw)
    return r, list(r.frames())


def leaked(outs, face=FACE):
    return [o.idx for o in outs if region_std(o.frame, face) >= 25]


def test_two_pass_covers_face_first_detected_beyond_the_lookahead():
    """The same scenario as test_KNOWN_LIMIT_* in test_pipeline.py, which stays pinned for LIVE mode."""
    script = {i: [det(FACE)] for i in range(10, 16)}
    _, outs = two_pass(script, 16, lookahead=4)
    assert leaked(outs) == []
    live = RedactionPipeline(ScriptedDetector(script), lookahead=4)
    live_outs = [o for i in range(16) for o in live.push(make_frame(i, FACE))] + live.flush()
    assert leaked(live_outs) == list(range(0, 6))                      # live mode still leaks: that is why the report warns


def test_KNOWN_LIMIT_blind_period_longer_than_back_extend_still_leaks():
    """Pins the limit: only the last `back_extend` frames before the first detection are covered."""
    script = {i: [det(FACE)] for i in range(30, 40)}
    _, outs = two_pass(script, 40, cfg=OfflineConfig(back_extend=16))
    assert leaked(outs) == list(range(0, 14))


def test_plan_keeps_geometry_only_no_pixels():
    fr = frames_of(20)
    plan = analyze(iter(fr), ScriptedDetector({i: [det(FACE)] for i in range(20)}))
    seen = []
    def walk(o, depth=0):
        if isinstance(o, np.ndarray):
            seen.append(o)
        elif isinstance(o, (list, tuple)):
            [walk(x, depth + 1) for x in o]
        elif isinstance(o, dict):
            [walk(x, depth + 1) for x in o.values()]
        elif hasattr(o, "__dict__") and depth < 6:
            [walk(x, depth + 1) for x in vars(o).values()]
    walk(plan)
    assert seen == []
    assert all(isinstance(x, int) for x in plan.fingerprints)           # a CRC of a 16x16 thumbnail, not an image


def test_fragments_separated_by_a_long_gap_become_one_person():
    script = {i: [det(FACE)] for i in list(range(0, 10)) + list(range(50, 60))}
    fr = frames_of(60)
    plan = analyze(iter(fr), ScriptedDetector(script))
    assert plan.summary["persons"] == 1 and plan.summary["stitched_links"] == 1
    assert {t.id for f in plan.tracks for t in f} == {1}
    live = RedactionPipeline(ScriptedDetector(script), lookahead=1)
    for f in fr:
        live.push(f)
    assert len(live.stats.tracks) == 2                                  # live ghost life (30) is shorter than the gap (40)


def test_two_faces_that_could_swap_places_are_not_merged_across_a_gap():
    a, b = Box(10, 40, 50, 80), Box(110, 40, 150, 80)
    script = {i: [det(a), det(b)] for i in range(0, 10)}
    script |= {i: [det(b)] for i in range(10, 60)}                      # A leaves for good; B stays
    plan = analyze(iter(frames_of(60)), ScriptedDetector(script))
    assert plan.summary["persons"] == 2


def test_gap_between_detections_is_covered_and_marked_interpolated():
    script = {i: [det(FACE)] for i in list(range(0, 10)) + list(range(13, 25))}
    fr = frames_of(25)
    plan = analyze(iter(fr), ScriptedDetector(script))
    gap = [plan.tracks[i][0] for i in (10, 11, 12)]
    assert all(t.is_ghost and t.interp_ok and t.gap_len == 3 for t in gap)
    assert all(t.box.x1 <= FACE.x1 and t.box.x2 >= FACE.x2 and t.box.y1 <= FACE.y1 and t.box.y2 >= FACE.y2 for t in gap)


def test_age_evidence_anywhere_on_a_person_applies_to_every_frame_of_that_person():
    script = {i: [det(FACE, 0.9, 0.9 if i >= 15 else None)] for i in range(20)}
    cfg = PolicyConfig(unknown_age_is_minor=False)                      # standard profile: unknown age alone is not escalated
    _, outs = two_pass(script, 20, policy=cfg)
    assert {o.treatments[1] for o in outs} == {"mosaic"}                # the minor-likely frames 15+ also protect frames 0-14
    live = RedactionPipeline(ScriptedDetector(script), cfg, lookahead=1)
    live_outs = [o for i in range(20) for o in live.push(make_frame(i, FACE))] + live.flush()
    assert live_outs[0].treatments[1] == "blur"                          # live mode only learns it at frame 15


def test_changed_source_between_passes_aborts_instead_of_emitting():
    script = {i: [det(FACE)] for i in range(10)}
    fr = frames_of(10)
    other = [make_frame(i + 500, FACE) for i in range(10)]
    state = {"n": 0}
    def open_frames():
        state["n"] += 1
        return iter(fr if state["n"] == 1 else other)
    with pytest.raises(PlanMismatchError):
        list(TwoPassRunner(open_frames, ScriptedDetector(script)).frames())


def test_shorter_source_in_pass_two_aborts():
    script = {i: [det(FACE)] for i in range(10)}
    fr = frames_of(10)
    state = {"n": 0}
    def open_frames():
        state["n"] += 1
        return iter(fr if state["n"] == 1 else fr[:7])
    with pytest.raises(PlanMismatchError):
        list(TwoPassRunner(open_frames, ScriptedDetector(script)).frames())


class FlakyDetector:
    name = "flaky"
    def __init__(self): self.i = -1
    def detect(self, f):
        self.i += 1
        if self.i == 5:
            raise RuntimeError("boom")
        return [det(FACE)]


def test_detector_failure_in_pass_one_blocks_that_frame_in_pass_two():
    fr = frames_of(12)
    r = TwoPassRunner(lambda: iter(fr), FlakyDetector())
    outs = list(r.frames())
    assert outs[5].scene_treatment == "block" and region_std(outs[5].frame, FACE) == 0.0
    assert r.pipeline.stats.detector_errors == 1


def test_swap_starts_without_the_five_frame_warm_up_in_two_pass_and_survives_a_short_gap():
    sv = SwapVerifier([FunctionRecognizer("A", lambda a, b: 0.1), FunctionRecognizer("B", lambda a, b: 0.1)])
    ids = IdentityAssigner(generate_stub_library(0), seed=1, allow_unvetted=True)
    script = {i: [det(FACE)] for i in range(40) if i not in (20, 21, 22)}
    r, outs = two_pass(script, 40, policy=PolicyConfig(swap_enabled=True), replacer=StubReplacer(), identities=ids,
                       swap_verifier=sv)
    k = [o.treatments.get(1) for o in outs]
    assert k[0] == "swap" and k[19] == "swap"                           # live mode shows mosaic for the first 4 frames
    assert k[20:23] == ["swap"] * 3                                     # 3-frame gap bracketed by detections: interpolated
    assert r.pipeline.stats.swap_demotions.get("ghost_track", 0) == 0


def test_long_gap_does_not_swap_and_unconfirmed_one_frame_track_never_swaps():
    sv = SwapVerifier([FunctionRecognizer("A", lambda a, b: 0.1), FunctionRecognizer("B", lambda a, b: 0.1)])
    ids = IdentityAssigner(generate_stub_library(0), seed=1, allow_unvetted=True)
    script = {i: [det(FACE)] for i in range(40) if not 20 <= i < 28}
    script[5] = script[5] + [det(Box(5, 5, 25, 25))]                    # a one-frame false positive
    r, outs = two_pass(script, 40, policy=PolicyConfig(swap_enabled=True), replacer=StubReplacer(), identities=ids,
                       swap_verifier=sv)
    k = [o.treatments.get(1) for o in outs]
    assert set(k[20:28]) == {"mosaic"}                                  # 8-frame gap > swap_interp_max_gap
    fp_ids = [t for t in r.pipeline.stats.tracks if t != 1]
    assert fp_ids and all("swap" not in r.pipeline.stats.tracks[t]["treatments"] or
                          r.pipeline.stats.tracks[t]["treatments"]["swap"] == 0 for t in fp_ids)


def test_report_states_mode_and_warns_in_live_mode_only():
    script = {i: [det(FACE)] for i in range(12)}
    r, _ = two_pass(script, 12)
    rep = PrivacyReport.build(r.pipeline, "x").data
    assert rep["mode"] == "two_pass" and rep["two_pass"]["persons"] == 1
    assert not any("Live mode" in w for w in rep["warnings"])
    live = RedactionPipeline(ScriptedDetector(script), lookahead=2)
    for i in range(12):
        live.push(make_frame(i, FACE))
    live.flush()
    lrep = PrivacyReport.build(live, "x").data
    assert lrep["mode"] == "live" and any("Live mode" in w for w in lrep["warnings"])
    assert "Two-pass analysis" in PrivacyReport.build(r.pipeline, "x").to_markdown()


def _release_run(release, gap):
    sv = SwapVerifier([FunctionRecognizer("A", lambda a, b: 0.1), FunctionRecognizer("B", lambda a, b: 0.1)])
    ids = IdentityAssigner(generate_stub_library(0), seed=1, allow_unvetted=True)
    script = {i: [det(FACE)] for i in range(60) if not 20 <= i < 20 + gap}
    pol = PolicyConfig(swap_enabled=True, swap_dropout_release_streak=release)
    r, outs = two_pass(script, 60, policy=pol, replacer=StubReplacer(), identities=ids, swap_verifier=sv)
    return [o.treatments.get(1) for o in outs]


def test_two_pass_releases_dropout_demotion_after_a_solid_streak_but_not_before():
    k = _release_run(release=-1, gap=8)                       # -1 = two-pass default (3)
    assert set(k[20:28]) == {"mosaic"}                        # still covered during the outage
    assert k[28] == "mosaic" and k[29] == "mosaic"            # streak of 1, 2 detections: not yet trusted
    assert k[30] == "swap"                                    # third consecutive detection releases (default sticky would hold to 43)
    held = _release_run(release=0, gap=8)                     # 0 = explicitly never early
    assert held[30] == "mosaic" and held[45] == "swap"


def test_early_release_never_applies_to_replacer_or_recognizer_demotions():
    sv = SwapVerifier([FunctionRecognizer("A", lambda a, b: 0.9)])        # always "matches the original": verification fails
    ids = IdentityAssigner(generate_stub_library(0), seed=1, allow_unvetted=True)
    script = {i: [det(FACE)] for i in range(40)}
    _, outs = two_pass(script, 40, policy=PolicyConfig(swap_enabled=True, swap_dropout_release_streak=1),
                       replacer=StubReplacer(), identities=ids, swap_verifier=sv)
    assert all(o.treatments.get(1) != "swap" for o in outs)
