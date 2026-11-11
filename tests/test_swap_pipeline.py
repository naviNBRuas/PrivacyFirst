import numpy as np
import pytest
from conftest import det, make_frame, W, H
from privacyfirst.detect import ScriptedDetector
from privacyfirst.identity import IdentityAssigner, generate_stub_library
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.policy import PolicyConfig
from privacyfirst.replace import StubReplacer
from privacyfirst.report import PrivacyReport
from privacyfirst.swapgate import FunctionRecognizer, SwapVerifier
from privacyfirst.types import Box

FACE = Box(60, 40, 100, 80)


def verifier(fail_from=None):
    n = {"c": 0}
    def r1(a, b):
        n["c"] += 1
        return 0.9 if (fail_from and n["c"] >= fail_from) else 0.1
    return SwapVerifier([FunctionRecognizer("recognizer-A", r1), FunctionRecognizer("recognizer-B", lambda a, b: 0.1)])


def mk(script, policy=None, health_fn=None, error_fn=None, sv="default", max_swaps=None, look=4, det_verifier=None, seed=1):
    cfg = policy or PolicyConfig(swap_enabled=True)
    ids = IdentityAssigner(generate_stub_library(0), seed=seed, allow_unvetted=True)
    return RedactionPipeline(ScriptedDetector(script), cfg, lookahead=look, replacer=StubReplacer(health_fn, error_fn),
                             identities=ids, swap_verifier=verifier() if sv == "default" else sv, max_swaps=max_swaps,
                             verifier=det_verifier)


def run(pipe, n, face=FACE):
    outs = []
    for i in range(n):
        outs += pipe.push(make_frame(i, face))
    return outs + pipe.flush()


def steady(n, boxes=(FACE,)):
    return {i: [det(b) for b in boxes] for i in range(n)}


def kinds(outs, tid=1):
    return [o.treatments.get(tid) for o in outs]


def test_requires_replacer_and_identities_when_enabled():
    with pytest.raises(ValueError):
        RedactionPipeline(ScriptedDetector({}), PolicyConfig(swap_enabled=True))


def test_new_track_is_mosaic_until_stable_then_swaps_with_one_stable_identity():
    pipe = mk(steady(40))
    outs = run(pipe, 40)
    k = kinds(outs)
    assert k[:4] == ["mosaic"] * 4 and set(k[4:]) == {"swap"}
    ident = pipe.swap_state[1].identity.id
    assert ident.startswith("stub-") and pipe.identities.by_track[1].id == ident
    raw = make_frame(10, FACE)
    assert np.abs(outs[10].frame.astype(int) - raw.astype(int))[40:80, 60:100].mean() > 20      # face was replaced
    assert PrivacyReport.build(pipe, "x").data["tracks"][0]["synthetic_identity_id"] == ident


def test_late_verification_failure_demotes_buffered_frames_and_stays_demoted():
    pipe = mk(steady(40), sv=verifier(fail_from=3), look=4)        # checks at idx 4, 9, 14 -> third fails
    outs = run(pipe, 40)
    k = kinds(outs)
    assert set(k[4:10]) == {"swap"} and set(k[10:]) == {"mosaic"}   # idx 10-13 were buffered and demoted at render
    assert pipe.stats.render_demotions == 4 and pipe.stats.verif_failures == 1
    rep = PrivacyReport.build(pipe, "x").data["swap"]
    assert rep["recognizer_verification"]["failures"] == 1 and "verification_failed" in rep["demotions_by_reason"]


def test_replacer_error_demotion_is_sticky_then_recovers_without_flicker():
    pipe = mk(steady(70), error_fn=lambda tid, i: i == 12)
    k = kinds(run(pipe, 70))
    assert set(k[12:42]) == {"mosaic"} and set(k[42:]) == {"swap"}
    changes = sum(1 for a, b in zip(k, k[1:]) if a != b)
    assert changes == 3     # mosaic(new) -> swap -> mosaic(one sticky window) -> swap: no flapping inside the window
    assert pipe.stats.replacer_errors == 1


def test_unhealthy_replacer_demotes_with_hysteresis():
    pipe = mk(steady(70), health_fn=lambda tid, i, b: 0.2 if i == 20 else 0.95)
    k = kinds(run(pipe, 70))
    assert set(k[20:50]) == {"mosaic"} and k[19] == "swap" and set(k[50:]) == {"swap"}


def test_two_people_never_share_an_identity_and_keep_theirs():
    boxes = (Box(20, 40, 60, 80), Box(100, 40, 140, 80))
    pipe = mk(steady(30, boxes))
    run(pipe, 30)
    a, b = pipe.swap_state[1].identity, pipe.swap_state[2].identity
    assert a.id != b.id
    rep = PrivacyReport.build(pipe, "x").data["tracks"]
    assert {t["synthetic_identity_id"] for t in rep} == {a.id, b.id}


def test_budget_overrun_demotes_smallest_face_to_blur():
    big, small = Box(20, 30, 70, 90), Box(110, 50, 135, 80)
    cfg = PolicyConfig(swap_enabled=True, unknown_age_is_minor=False)
    script = {i: [det(big, 0.9, 0.0), det(small, 0.9, 0.0)] for i in range(30)}
    pipe = mk(script, policy=cfg, max_swaps=1)
    outs = run(pipe, 30)
    assert set(kinds(outs, 1)[6:]) == {"swap"} and set(kinds(outs, 2)[6:]) == {"blur"}


def test_minor_risk_never_swaps_without_recognizer_verification():
    pipe = mk(steady(30), sv=None)
    outs = run(pipe, 30)
    assert set(kinds(outs)) == {"mosaic"}
    w = PrivacyReport.build(pipe, "x").data["warnings"]
    assert any("No recognizer-ensemble" in x for x in w) and any("Stub replacer" in x for x in w)
    assert any("Unvetted identity library" in x for x in w)


def test_single_recognizer_ensemble_is_too_small_so_no_minor_swap():
    one = SwapVerifier([FunctionRecognizer("only", lambda a, b: 0.0)])
    pipe = mk(steady(30), sv=one)
    assert set(kinds(run(pipe, 30))) == {"mosaic"}


def test_residual_face_scan_ignores_swapped_head_but_still_catches_other_leaks():
    class SeesFace:
        name = "residual-detector"
        def detect(self, f): return [det(FACE)]
    pipe = mk(steady(30), det_verifier=SeesFace())
    outs = run(pipe, 30)
    assert all("verifier_escalated" not in o.notes for o in outs[4:])
    assert all(o.frame.max() > 0 for o in outs[4:])
    assert any("verifier_escalated" in o.notes for o in outs[:4])      # mosaic frames are still scanned


def test_identity_is_released_when_track_ends():
    script = {i: [det(FACE)] for i in range(10)}
    pipe = mk(script)
    run(pipe, 60)
    assert pipe.identities.by_track == {} and pipe.swap_state[1].identity is None


def test_swap_output_always_geometrically_covers_the_face():
    pipe = mk(steady(40))
    for o in run(pipe, 40):
        assert any(b.x1 <= FACE.x1 and b.y1 <= FACE.y1 and b.x2 >= FACE.x2 and b.y2 >= FACE.y2 for _, b, _ in o.regions)


def test_detector_failure_still_blocks_frame_with_swap_on():
    class Boom:
        name = "boom"
        def detect(self, f): raise RuntimeError("x")
    ids = IdentityAssigner(generate_stub_library(0), seed=1, allow_unvetted=True)
    pipe = RedactionPipeline(Boom(), PolicyConfig(swap_enabled=True), lookahead=1, replacer=StubReplacer(), identities=ids)
    assert all(o.frame.max() == 0 for o in run(pipe, 3))
