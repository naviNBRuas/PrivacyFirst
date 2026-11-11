from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from ..pipeline import RedactionPipeline
from ..policy import PolicyConfig
from ..offline import TwoPassRunner
from ..tracking import LegacyIoUTracker, Tracker
from ..types import Box
from .metrics import score_clip
from .simdet import SimulatedDetector
from .synth import SCENARIOS, Clip, make_clip

# name -> (lookahead, max_ghost_frames)
VARIANTS = {
    "detect_only": (1, 0),        # no ghost tracks, no meaningful backfill: raw detector behaviour
    "ghost": (1, 30),
    "ghost+look4": (4, 30),
    "ghost+look8": (8, 30),
    "ghost+look16": (16, 30),
    "legacy_tracker+look4": (4, 30),   # run 001-003 tracker (greedy IoU, no hull), for A/B against ghost+look4
    "two_pass": (4, 30),               # recorded mode: whole-file analysis, then render (offline.py)
}


class _Recorder:
    def __init__(self, inner):
        self.inner, self.name, self.log = inner, inner.name, []
    def detect(self, f):
        d = list(self.inner.detect(f)); self.log.append(d); return d


def run_variant(clip: Clip, frames: list[np.ndarray], variant: str, seed: int = 0,
                policy: PolicyConfig | None = None) -> dict:
    look, ghost = VARIANTS[variant]
    rec = _Recorder(SimulatedDetector(clip, seed))
    pol = policy or PolicyConfig.strict()
    if variant == "two_pass":
        runner = TwoPassRunner(lambda: iter(frames), rec, pol, lookahead=look)
        outs = list(runner.frames())
        return score_clip(clip, outs, rec.log)
    trk = LegacyIoUTracker(max_ghost_frames=ghost) if variant == "legacy_tracker+look4" else Tracker(max_ghost_frames=ghost)
    pipe = RedactionPipeline(rec, pol, lookahead=look, tracker=trk)
    outs = []
    for f in frames:
        outs += pipe.push(f)
    outs += pipe.flush()
    return score_clip(clip, outs, rec.log)


def run_benchmark(scenarios=None, seeds=5, n_frames=120, variants=None) -> dict:
    scenarios = scenarios or SCENARIOS
    variants = variants or list(VARIANTS)
    agg: dict = {}
    for sc in scenarios:
        for seed in range(seeds):
            clip = make_clip(sc, seed, n_frames)
            frames = list(clip.frames())
            for v in variants:
                r = run_variant(clip, frames, v, seed)
                a = agg.setdefault(sc, {}).setdefault(v, {k: 0.0 for k in r if k != "min_coverage"} | {"min_coverage": 1.0})
                for k, val in r.items():
                    a[k] = min(a[k], val) if k == "min_coverage" else a[k] + val
    for sc, vs in agg.items():
        for v, a in vs.items():
            n = max(1, a["visible_face_frames"])
            a["leak_rate"] = a["leaked_face_frames"] / n
            a["severe_leak_rate"] = a["severe_leaked_face_frames"] / n
            a["detector_miss_rate"] = a["detector_missed_face_frames"] / n
            a["mean_redacted_area_frac"] /= seeds
    return {"seeds": seeds, "frames_per_clip": n_frames, "variants": variants, "results": agg,
            "note": "SIMULATED detector failure modes. Measures pipeline behaviour, not real detector accuracy."}


def to_markdown(res: dict) -> str:
    vs = res["variants"]
    L = ["# Benchmark: leak rate by scenario and pipeline variant", "",
         f"Seeds: {res['seeds']}, frames/clip: {res['frames_per_clip']}. **{res['note']}**", "",
         "Leak rate = share of visible face-frames with <90% of the face box covered by redaction. Lower is better.", "",
         "| Scenario | Detector miss | " + " | ".join(vs) + " |", "|---|---|" + "---|" * len(vs)]
    for sc, d in res["results"].items():
        miss = d[vs[0]]["detector_miss_rate"]
        L.append(f"| {sc} | {miss:.1%} | " + " | ".join(f"{d[v]['leak_rate']:.1%}" for v in vs) + " |")
    L += ["", "## Cost: mean share of the frame that is redacted", "",
          "| Scenario | " + " | ".join(vs) + " |", "|---|" + "---|" * len(vs)]
    for sc, d in res["results"].items():
        L.append(f"| {sc} | " + " | ".join(f"{d[v]['mean_redacted_area_frac']:.1%}" for v in vs) + " |")
    L += ["", "## Track-ID changes per scenario (matters for stable synthetic identity in Phase 2)", "",
          "| Scenario | " + " | ".join(vs) + " |", "|---|" + "---|" * len(vs)]
    for sc, d in res["results"].items():
        L.append(f"| {sc} | " + " | ".join(str(int(d[v]['track_id_changes'])) for v in vs) + " |")
    return "\n".join(L) + "\n"


def plot(res: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vs, sc = res["variants"], list(res["results"])
    fig, ax = plt.subplots(figsize=(13, 4.8))
    w = 0.8 / (len(vs) + 1)
    x = np.arange(len(sc))
    ax.bar(x - 0.4 + w / 2, [res["results"][s][vs[0]]["detector_miss_rate"] * 100 for s in sc], w,
           label="raw detector miss", color="#9aa0a6")
    for i, v in enumerate(vs):
        ax.bar(x - 0.4 + w * (i + 1.5), [res["results"][s][v]["leak_rate"] * 100 for s in sc], w, label=f"leak: {v}")
    ax.set_xticks(x); ax.set_xticklabels(sc, rotation=25, ha="right")
    ax.set_ylabel("% of visible face-frames not covered"); ax.set_title("Leak rate by scenario (SIMULATED detector failures)")
    ax.legend(fontsize=8, ncol=3); ax.grid(axis="y", alpha=.3); fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def evaluate_detector(detector, clips: list[Clip], iou_thr: float = 0.5) -> dict:
    """Recall@IoU, false positives per image, and latency for ANY detector on clips with ground truth."""
    tp = fn = fp = n_img = 0
    lat: list[float] = []
    for clip in clips:
        for i, f in enumerate(clip.frames()):
            t0 = time.perf_counter(); dets = list(detector.detect(f)); lat.append((time.perf_counter() - t0) * 1000)
            n_img += 1
            vis = [g for g in clip.gt[i] if g.visible]
            used = set()
            for g in vis:
                hit = None
                for j, d in enumerate(dets):
                    if j not in used and g.box.iou(d.box) >= iou_thr:
                        hit = j; break
                if hit is None: fn += 1
                else: tp += 1; used.add(hit)
            fp += len(dets) - len(used)
    lat_a = np.array(lat) if lat else np.zeros(1)
    return {"detector": detector.name, "images": n_img, "recall": tp / max(1, tp + fn), "fppi": fp / max(1, n_img),
            "latency_ms": {"mean": float(lat_a.mean()), "p50": float(np.percentile(lat_a, 50)), "p95": float(np.percentile(lat_a, 95))}}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m privacyfirst.bench")
    ap.add_argument("--out", default="runs/bench"); ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--frames", type=int, default=120)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    res = run_benchmark(seeds=a.seeds, n_frames=a.frames)
    (out / "benchmark.json").write_text(json.dumps(res, indent=2))
    (out / "benchmark.md").write_text(to_markdown(res))
    plot(res, out / "benchmark_leak_rate.png")
    print(to_markdown(res))
    return 0
