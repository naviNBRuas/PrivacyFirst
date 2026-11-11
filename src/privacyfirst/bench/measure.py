"""Measure a REAL detector on REAL footage in the simulator's terms (run 005 kit).

No ground truth is needed, so every number is a HEURISTIC estimate from detections + the tracker:
  * a "miss burst" is a run of frames where a track (>= min_hits detections) had no detection and was later re-detected.
    It also counts genuine occlusions and exits-and-returns, so p_enter_miss / mean_burst are UPPER-ish bounds.
  * false positives are bounded above by tracks that live <= 2 detections (real brief faces are counted too).
  * min_size is the 5th percentile of detected face size, not the true detection floor.
Use the output to replace guessed DetectorProfile values, then rerun the benchmarks. Treat the first numbers as a
starting point and check a handful of bursts by eye.

Usage: python -m privacyfirst.bench.measure VIDEO [VIDEO...] --detector yunet --model-dir DIR [--out report.json]
"""
from __future__ import annotations
import argparse
import json
import statistics
from pathlib import Path
from typing import Sequence
from ..tracking import Tracker
from ..types import Detection


def _q(xs: Sequence[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def estimate(dets_log: list[list[Detection]], w: int, h: int, min_hits: int = 5) -> dict:
    tr = Tracker()
    obs: dict[int, list[int]] = {}
    for i, dets in enumerate(dets_log):
        for t in tr.update(dets, w, h):
            if t.misses == 0:
                obs.setdefault(t.id, []).append(i)
    all_d = [d for ds in dets_log for d in ds]
    bursts, det_frames, short = [], 0, 0
    for fr in obs.values():
        if len(fr) <= 2:
            short += 1
        if len(fr) < min_hits:
            continue
        det_frames += len(fr)
        bursts += [b - a - 1 for a, b in zip(fr, fr[1:]) if b - a > 1]
    n = max(1, len(dets_log))
    sizes = [(d.box.w * d.box.h) ** 0.5 for d in all_d]
    return {
        "frames": len(dets_log), "detections": len(all_d), "tracks": len(obs),
        "confidence": {"median": _q([d.conf for d in all_d], 0.5), "p10": _q([d.conf for d in all_d], 0.1)},
        "face_size_px": {"p5": _q(sizes, 0.05), "median": _q(sizes, 0.5)},
        "miss_bursts": {"count": len(bursts), "mean_len": statistics.fmean(bursts) if bursts else 0.0,
                        "p90_len": _q(bursts, 0.9), "max_len": max(bursts, default=0)},
        "suggested_profile": {
            "p_enter_miss": len(bursts) / max(1, det_frames),
            "mean_burst": statistics.fmean(bursts) if bursts else 0.0,
            "min_size": _q(sizes, 0.05),
            "fp_per_frame_upper_bound": short / n,
            "base_conf": _q([d.conf for d in all_d], 0.5),
        },
        "caveat": "heuristic, no ground truth; occlusions and exits count as misses; verify by eye before calibrating",
    }


def main(argv=None) -> int:
    import cv2
    from ..detectors import make_detector
    ap = argparse.ArgumentParser(prog="python -m privacyfirst.bench.measure")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--detector", default="yunet", choices=["haar", "yunet", "mediapipe"])
    ap.add_argument("--model-dir")
    ap.add_argument("--out", default="detector_measurement.json")
    a = ap.parse_args(argv)
    det = make_detector(a.detector, a.model_dir)
    report = {"detector": getattr(det, "name", a.detector), "videos": {}}
    for v in a.videos:
        cap = cv2.VideoCapture(v)
        if not cap.isOpened():
            print(f"cannot open {v}")
            return 2
        log, w, h = [], 0, 0
        while True:
            ok, f = cap.read()
            if not ok:
                break
            h, w = f.shape[:2]
            log.append(list(det.detect(f)))
        cap.release()
        report["videos"][Path(v).name] = estimate(log, w, h)
    Path(a.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
