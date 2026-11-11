import json
import cv2
import numpy as np
from privacyfirst.cli import main


def _noise_video(path, n=12):
    rng = np.random.default_rng(0)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 72))
    for _ in range(n):
        vw.write(rng.integers(60, 200, (72, 96, 3), dtype=np.uint8))
    vw.release()


def test_video_defaults_to_two_pass_and_reports_it(tmp_path):
    src, dst, rj = tmp_path / "in.mp4", tmp_path / "out.mp4", tmp_path / "r.json"
    _noise_video(src)
    assert main(["video", str(src), str(dst), "--report-json", str(rj)]) == 0
    rep = json.loads(rj.read_text())
    assert rep["mode"] == "two_pass" and rep["frames"] == {"in": 12, "out": 12} and dst.exists()
    assert not any("Live mode" in w for w in rep["warnings"])


def test_video_live_mode_is_still_available_and_warns(tmp_path):
    src, dst, rj = tmp_path / "in.mp4", tmp_path / "out.mp4", tmp_path / "r.json"
    _noise_video(src)
    assert main(["video", str(src), str(dst), "--mode", "live", "--report-json", str(rj)]) == 0
    rep = json.loads(rj.read_text())
    assert rep["mode"] == "live" and any("Live mode" in w for w in rep["warnings"])


def test_unreadable_input_returns_error_without_output(tmp_path):
    dst = tmp_path / "out.mp4"
    assert main(["video", str(tmp_path / "missing.mp4"), str(dst)]) == 2 and not dst.exists()


def test_missing_real_detector_weights_fail_loudly_not_silently(tmp_path, monkeypatch):
    monkeypatch.delenv("PRIVACYFIRST_MODEL_DIR", raising=False)
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _noise_video(src)
    assert main(["video", str(src), str(dst), "--detector", "yunet", "--model-dir", str(tmp_path / "none")]) == 2
    assert not dst.exists()
