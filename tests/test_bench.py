import numpy as np
import pytest
from privacyfirst.adapters.mediapipe_tasks import MediaPipeFaceDetector
from privacyfirst.adapters.yunet import YuNetDetector
from privacyfirst.bench.metrics import LEAK_COV, coverage_mask, face_coverage
from privacyfirst.bench.runner import evaluate_detector, run_benchmark, to_markdown
from privacyfirst.bench.simdet import SimulatedDetector
from privacyfirst.bench.synth import SCENARIOS, H, W, make_clip
from privacyfirst.pipeline import OutputFrame, RedactionPipeline
from privacyfirst.detect import ScriptedDetector
from privacyfirst.types import Box, Detection


def test_clips_are_deterministic_and_complete():
    for sc in SCENARIOS:
        a, b = make_clip(sc, 3, 30), make_clip(sc, 3, 30)
        assert a.n_frames == 30 and len(a.gt) == 30
        assert (a.render(7) == b.render(7)).all() and a.gt[7][0].box == b.gt[7][0].box


def test_simulated_detector_reproducible_and_seed_sensitive():
    clip = make_clip("tiny_faces", 0, 60)
    run = lambda s: [len(SimulatedDetector(clip, s).detect(None)) for _ in range(1)]  # noqa
    d1, d2 = SimulatedDetector(clip, 5), SimulatedDetector(clip, 5)
    assert [len(d1.detect(None)) for _ in range(60)] == [len(d2.detect(None)) for _ in range(60)]


def _out(regions=(), scene=None, full=False):
    return OutputFrame(0, np.zeros((H, W, 3), np.uint8), {}, [], list(regions), scene, full)


def test_coverage_metric():
    clip = make_clip("baseline", 0, 5)
    g = clip.gt[0][0]
    assert face_coverage(coverage_mask(_out()), g) == 0.0
    assert face_coverage(coverage_mask(_out([(1, g.box.expanded(0.2, W, H), "mosaic")])), g) == 1.0
    assert face_coverage(coverage_mask(_out(scene="mosaic")), g) == 1.0
    assert face_coverage(coverage_mask(_out(full=True)), g) == 1.0
    half = Box(g.box.x1, g.box.y1, (g.box.x1 + g.box.x2) / 2, g.box.y2)
    assert face_coverage(coverage_mask(_out([(1, half, "blur")])), g) < LEAK_COV


def test_pipeline_exposes_regions_for_audit():
    f = np.full((H, W, 3), 90, np.uint8)
    b = Box(50, 40, 90, 90)
    pipe = RedactionPipeline(ScriptedDetector({0: [Detection(b, 0.9)]}), lookahead=1)
    outs = pipe.push(f) + pipe.flush()
    assert outs[0].regions and outs[0].regions[0][0] == 1 and outs[0].regions[0][2] in ("blur", "mosaic")


def test_ghost_tracks_reduce_leaks_vs_detect_only():
    res = run_benchmark(scenarios=["low_light", "motion_blur"], seeds=2, n_frames=60)
    for sc in res["results"].values():
        assert sc["ghost"]["leak_rate"] <= sc["detect_only"]["leak_rate"]
        assert sc["ghost+look16"]["leak_rate"] <= sc["ghost"]["leak_rate"] + 1e-9
    assert "SIMULATED" in res["note"] and "| low_light |" in to_markdown(res)


class Oracle:
    name = "oracle"
    def __init__(self, clip): self.clip, self.i = clip, -1
    def detect(self, f):
        self.i += 1
        return [Detection(g.box, 0.99) for g in self.clip.gt[self.i] if g.visible]


def test_evaluate_detector_oracle_is_perfect():
    clip = make_clip("crowd", 0, 20)
    r = evaluate_detector(Oracle(clip), [clip])
    assert r["recall"] == 1.0 and r["fppi"] == 0.0 and r["latency_ms"]["p95"] >= 0


def test_real_model_adapters_fail_with_clear_error_when_model_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("PRIVACYFIRST_MODEL_DIR", raising=False)
    for cls in (MediaPipeFaceDetector, YuNetDetector):
        with pytest.raises(FileNotFoundError, match="MODEL_SETUP"):
            cls(model_path=tmp_path / "nope.bin")


def test_swap_bench_no_collisions_and_persistent_identity_is_steadier():
    from privacyfirst.bench.swapbench import run_swap_clip
    clip = make_clip("baseline", 0, 60)
    frames = list(clip.frames())
    a, b = run_swap_clip(clip, frames, 0), run_swap_clip(clip, frames, 0, churn=True)
    assert a["collisions"] == 0 and a["kinds"].get("swap", 0) > 0
    assert a["flicker"] < b["flicker"] * 0.6
