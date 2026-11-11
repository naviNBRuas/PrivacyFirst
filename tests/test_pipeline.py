import numpy as np
from privacyfirst.detect import ScriptedDetector
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.report import PrivacyReport, verification_status
from privacyfirst.types import Box, Detection
from conftest import make_frame, region_std, det, W, H


def run(pipe, n, face):
    outs = []
    for i in range(n):
        outs += pipe.push(make_frame(i, face))
    outs += pipe.flush()
    return outs


def test_every_frame_is_redacted_including_detector_dropouts(face):
    script = {i: [det(face)] for i in range(20) if i not in range(8, 12)}   # 4-frame dropout
    pipe = RedactionPipeline(ScriptedDetector(script), lookahead=4)
    outs = run(pipe, 20, face)
    assert [o.idx for o in outs] == list(range(20))
    for o in outs:
        assert region_std(o.frame, face) < 25, f"frame {o.idx} left face texture visible"


def test_backfill_covers_buffered_frames_before_first_detection(face):
    script = {i: [det(face)] for i in range(6, 14)}          # face present from 0 but first detected at 6
    pipe = RedactionPipeline(ScriptedDetector(script), lookahead=4)
    outs = run(pipe, 14, face)
    covered = [o.idx for o in outs if region_std(o.frame, face) < 25]
    assert all(i in covered for i in range(2, 14))           # frames 2-5 backfilled, 6+ detected
    assert pipe.stats.backfilled_regions >= 4


def test_detector_exception_blocks_whole_frame(face):
    class Boom:
        name = "boom"
        def detect(self, f): raise RuntimeError("model crashed")
    pipe = RedactionPipeline(Boom(), lookahead=1)
    outs = run(pipe, 3, face)
    assert all(o.frame.max() == 0 for o in outs)
    assert pipe.stats.detector_errors == 3


def test_dark_scene_is_not_trusted(face):
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1)
    dark = np.zeros((H, W, 3), np.uint8)
    out = pipe.push(dark) + pipe.flush()
    assert pipe.stats.scene_events["scene_too_dark_to_trust_detection"] == 1


def test_lookahead_delays_output(face):
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=4)
    assert sum(len(pipe.push(make_frame(i))) for i in range(4)) == 0
    assert len(pipe.flush()) == 4


def test_verifier_escalates_residual_face_then_passes(face):
    class OnceResidual:
        name = "verifier"
        def __init__(self): self.n = 0
        def detect(self, f):
            self.n += 1
            return [Detection(face, 0.9)] if self.n == 1 else []
    pipe = RedactionPipeline(ScriptedDetector({0: [det(face)]}), lookahead=1, verifier=OnceResidual())
    outs = run(pipe, 1, face)
    assert verification_status(pipe) == "passed_after_escalation"
    assert region_std(outs[0].frame, face) == 0.0


def test_persistent_residual_blocks_frame_and_fails_verification(face):
    class AlwaysSees:
        name = "verifier"
        def detect(self, f): return [Detection(face, 0.9)]
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1, verifier=AlwaysSees())
    outs = run(pipe, 2, face)
    assert all(o.frame.max() == 0 for o in outs)
    assert verification_status(pipe) == "failed_frames_blocked"


def test_report_has_no_pixel_or_embedding_payload_and_flags_placeholder(face):
    class P:
        name = "opencv-haar (placeholder)"
        def detect(self, f): return [det(face)]
    pipe = RedactionPipeline(P(), lookahead=2)
    run(pipe, 6, face)
    rep = PrivacyReport.build(pipe, "clip.mp4")
    js = rep.to_json()
    assert "Placeholder detector" in js and "residual_risk_statement" in js
    assert rep.data["tracks"][0]["treated_as_minor_risk"] is True
    assert "embedding" not in js.lower().replace("embeddings", "")  # no embedding fields
    assert "# Privacy Report" in rep.to_markdown()


def test_KNOWN_LIMIT_face_first_detected_beyond_lookahead_leaks_earlier_frames(face):
    """Characterization test, documents a limit rather than endorsing it.

    A bounded live buffer cannot redact frames it has already emitted. Frames emitted before the
    first detection are NOT covered. Recorded-video mode must use a two-pass design (Phase 1b)
    to close this; see docs/KNOWN_LIMITATIONS.md. If this test starts failing because the leak is
    fixed, flip it into a positive coverage test.
    """
    script = {i: [det(face)] for i in range(10, 16)}
    pipe = RedactionPipeline(ScriptedDetector(script), lookahead=4)
    outs = run(pipe, 16, face)
    leaked = [o.idx for o in outs if region_std(o.frame, face) >= 25]
    assert leaked == list(range(0, 6))
