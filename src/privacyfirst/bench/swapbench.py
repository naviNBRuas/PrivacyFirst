"""Benchmark of the face-change (SWAP) path with the STUB replacer under simulated detector failures.

Measures what the gates do, not how good a real swap model is: how much of each scenario ends up as swap vs
fallback, whether any face is uncovered, whether one person keeps one identity (tracker fragmentation shows up
here), whether identities ever collide, and a temporal-stability (flicker) comparison between a persistent
identity per person and a counterfactual that re-picks an identity every frame.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
from ..identity import IdentityAssigner, generate_stub_library
from ..pipeline import RedactionPipeline
from ..offline import TwoPassRunner
from ..policy import PolicyConfig
from ..replace import StubReplacer
from ..stabilize import flicker_score
from ..swapgate import FunctionRecognizer, SwapVerifier
from .metrics import LEAK_COV, coverage_mask, face_coverage
from .runner import _Recorder
from .simdet import SimulatedDetector
from .synth import SCENARIOS, Clip, make_clip


class ChurnReplacer(StubReplacer):
    """Counterfactual: ignores the assigned identity and re-picks one every frame (what NOT to do)."""
    name = "stub-replacer-churn (counterfactual)"

    def __init__(self, library, **kw):
        super().__init__(**kw)
        self._lib = library.identities

    def replace(self, frame, track, head_box, identity, frame_idx):
        return super().replace(frame, track, head_box, self._lib[(frame_idx * 7 + track.id * 3) % len(self._lib)], frame_idx)


def _crop32(out_frame, box):
    x1, y1, x2, y2 = box.clamp_int(out_frame.shape[1], out_frame.shape[0])
    c = out_frame[y1:y2, x1:x2]
    return cv2.resize(c, (32, 32), interpolation=cv2.INTER_AREA) if c.size else None


def run_swap_clip(clip: Clip, frames, seed: int, churn: bool = False, lookahead: int = 4, mode: str = "live",
                  policy: PolicyConfig | None = None, tracker=None) -> dict:
    lib = generate_stub_library(0, per_cell=6)
    ids = IdentityAssigner(lib, seed=seed + 17, allow_unvetted=True)
    rep = ChurnReplacer(lib) if churn else StubReplacer()
    sv = SwapVerifier([FunctionRecognizer("sim-A", lambda a, b: 0.1), FunctionRecognizer("sim-B", lambda a, b: 0.1)])
    rec = _Recorder(SimulatedDetector(clip, seed))
    pol = policy or PolicyConfig(swap_enabled=True)
    if mode == "two_pass":
        runner = TwoPassRunner(lambda: iter(frames), rec, pol, lookahead=lookahead, replacer=rep, identities=ids,
                               swap_verifier=sv)
        outs = list(runner.frames())
        pipe = runner.pipeline
    else:
        kw = {"tracker": tracker} if tracker is not None else {}
        pipe = RedactionPipeline(rec, pol, lookahead=lookahead, replacer=rep, identities=ids, swap_verifier=sv, **kw)
        outs = []
        for f in frames:
            outs += pipe.push(f)
        outs += pipe.flush()
    ident = {tid: t["identity_id"] for tid, t in pipe.stats.tracks.items()}
    kinds: Counter = Counter()
    per_face_ids: dict[int, set] = {}
    leaked = faces = collisions = 0
    seq: dict[int, list] = {}                         # gt face id -> treatment kind per frame, for alternation counting
    crops: dict[int, list] = {}
    for o in outs:
        mask = coverage_mask(o)
        seen = [ident.get(t) for t, _, tr in o.regions if t >= 0 and tr == "swap" and ident.get(t)]
        collisions += len(seen) - len(set(seen))
        for tid, box, tr in o.regions:
            if tr == "swap":
                c = _crop32(o.frame, box)
                if c is not None:
                    crops.setdefault(tid, []).append((o.idx, c))
        for g in clip.gt[o.idx]:
            if not g.visible:
                continue
            faces += 1
            leaked += int(face_coverage(mask, g) < LEAK_COV)
            best, kind, btid = 0.1, "uncovered", None
            for tid, box, tr in o.regions:
                if tid >= 0 and g.box.iou(box) > best:
                    best, kind, btid = g.box.iou(box), tr, tid
            kinds[kind] += 1
            seq.setdefault(g.id, []).append(kind)
            if kind == "swap" and ident.get(btid):
                per_face_ids.setdefault(g.id, set()).add(ident[btid])
    fl = []
    for lst in crops.values():                       # flicker over consecutive swapped frames of each track
        lst.sort(key=lambda x: x[0])
        run = [lst[0][1]]
        for (i0, _), (i1, c) in zip(lst, lst[1:]):
            if i1 == i0 + 1:
                run.append(c)
            else:
                if len(run) > 1:
                    fl.append(flicker_score(run))
                run = [c]
        if len(run) > 1:
            fl.append(flicker_score(run))
    trans = sum(1 for v in seq.values() for a, b in zip(v, v[1:]) if a != b and "swap" in (a, b))
    return {"faces": faces, "kinds": dict(kinds), "leaked": leaked, "collisions": collisions, "transitions": trans,
            "identity_changes": sum(max(0, len(v) - 1) for v in per_face_ids.values()),
            "faces_with_identity": len(per_face_ids), "demotions": dict(pipe.stats.swap_demotions),
            "flicker": float(np.mean(fl)) if fl else None}


def run_swap_benchmark(seeds: int = 3, n_frames: int = 120, mode: str = "live", policy: PolicyConfig | None = None,
                       tracker_factory=None, scenarios=None, with_churn: bool = True) -> dict:
    res: dict = {}
    for sc in (scenarios or SCENARIOS):
        agg = {"faces": 0, "kinds": Counter(), "leaked": 0, "collisions": 0, "identity_changes": 0,
               "faces_with_identity": 0, "demotions": Counter(), "flicker": [], "flicker_churn": [], "transitions": 0}
        for seed in range(seeds):
            clip = make_clip(sc, seed, n_frames)
            frames = list(clip.frames())
            kw = dict(mode=mode, policy=policy, tracker=tracker_factory() if tracker_factory else None)
            r = run_swap_clip(clip, frames, seed, **kw)
            c = run_swap_clip(clip, frames, seed, churn=True, **kw) if with_churn else {"flicker": None}
            for k in ("faces", "leaked", "collisions", "identity_changes", "faces_with_identity", "transitions"):
                agg[k] += r[k]
            agg["kinds"].update(r["kinds"]); agg["demotions"].update(r["demotions"])
            if r["flicker"] is not None: agg["flicker"].append(r["flicker"])
            if c["flicker"] is not None: agg["flicker_churn"].append(c["flicker"])
        n = max(1, agg["faces"])
        res[sc] = {"faces": agg["faces"], "swap": agg["kinds"]["swap"] / n, "mosaic": agg["kinds"]["mosaic"] / n,
                   "blur": agg["kinds"]["blur"] / n, "block": agg["kinds"]["block"] / n,
                   "uncovered": agg["kinds"]["uncovered"] / n, "leak_rate": agg["leaked"] / n,
                   "collisions": agg["collisions"], "transitions_per_100": 100.0 * agg["transitions"] / n,
                   "identity_changes_per_face": agg["identity_changes"] / max(1, agg["faces_with_identity"]),
                   "demotions": dict(agg["demotions"]),
                   "flicker_persistent": float(np.mean(agg["flicker"])) if agg["flicker"] else None,
                   "flicker_churn": float(np.mean(agg["flicker_churn"])) if agg["flicker_churn"] else None}
    return {"seeds": seeds, "frames_per_clip": n_frames, "mode": mode, "results": res,
            "note": "STUB replacer + SIMULATED detector. Measures the gates and bookkeeping, not real swap quality."}


def to_markdown(res: dict) -> str:
    L = ["# Face-change (swap) benchmark", "", f"Seeds: {res['seeds']}, frames/clip: {res['frames_per_clip']}. **{res['note']}**", "",
         "Shares are of visible face-frames, by the treatment actually applied. Strict profile: unknown age is minor-risk, "
         "so every swap needed an explicit recognizer-ensemble PASS.", "",
         "| Scenario | Swap | Mosaic | Blur | Block | Uncovered | Leak rate | Identity changes / person | Collisions |",
         "|---|---|---|---|---|---|---|---|---|"]
    for sc, r in res["results"].items():
        L.append(f"| {sc} | {r['swap']:.0%} | {r['mosaic']:.0%} | {r['blur']:.0%} | {r['block']:.0%} | {r['uncovered']:.1%} | "
                 f"{r['leak_rate']:.1%} | {r['identity_changes_per_face']:.2f} | {r['collisions']} |")
    L += ["", "## Why faces were demoted from swap (counts)", "", "| Scenario | Reasons |", "|---|---|"]
    for sc, r in res["results"].items():
        L.append(f"| {sc} | {', '.join(f'{k}: {v}' for k, v in sorted(r['demotions'].items(), key=lambda kv: -kv[1])[:5]) or 'none'} |")
    L += ["", "## Temporal stability: persistent identity vs re-picking every frame (flicker, lower = steadier)", "",
          "| Scenario | Persistent | Churn counterfactual |", "|---|---|---|"]
    for sc, r in res["results"].items():
        if r["flicker_persistent"] is not None and r["flicker_churn"] is not None:
            L.append(f"| {sc} | {r['flicker_persistent']:.1f} | {r['flicker_churn']:.1f} |")
    return "\n".join(L) + "\n"


def summarize(res: dict) -> dict:
    R = res["results"]
    F = max(1, sum(r["faces"] for r in R.values()))
    w = lambda k: sum(r[k] * r["faces"] for r in R.values()) / F
    return {"swap_share": w("swap"), "leak_rate": w("leak_rate"), "transitions_per_100": w("transitions_per_100"),
            "identity_changes_per_person": sum(r["identity_changes_per_face"] for r in R.values()) / max(1, len(R)),
            "collisions": sum(r["collisions"] for r in R.values())}


def combined_markdown(runs: dict) -> str:
    L = ["# Face-change benchmark: tracker and mode comparison (run 004)", "",
         "All configurations use the same clips, seeds and default policy. **STUB replacer + SIMULATED detector.** "
         "Leak rate counts a swapped head box as covered (limitation 22), so it does not judge swap quality. "
         "Averages are weighted by face-frames across all scenarios.", "",
         "| Configuration | Swap share | Leak rate | Identity changes / person | Swap<->fallback flips / 100 face-frames | Collisions |",
         "|---|---|---|---|---|---|"]
    for name, r in runs.items():
        s = summarize(r)
        L.append(f"| {name} | {s['swap_share']:.1%} | {s['leak_rate']:.2%} | {s['identity_changes_per_person']:.2f} | "
                 f"{s['transitions_per_100']:.1f} | {s['collisions']} |")
    for name, r in runs.items():
        L += ["", f"## {name}", "", to_markdown(r).split("\n", 2)[2]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    import argparse
    from ..tracking import LegacyIoUTracker
    ap = argparse.ArgumentParser(prog="python -m privacyfirst.bench.swapbench")
    ap.add_argument("--out", default="runs/bench"); ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--frames", type=int, default=120)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    runs = {
        "live, legacy tracker (current gates)": run_swap_benchmark(a.seeds, a.frames, "live", tracker_factory=LegacyIoUTracker, with_churn=False),
        "live, run-004 tracker": run_swap_benchmark(a.seeds, a.frames, "live"),
        "two-pass": run_swap_benchmark(a.seeds, a.frames, "two_pass", with_churn=False),
    }
    (out / "swap_benchmark.json").write_text(json.dumps(runs, indent=2))
    md = combined_markdown(runs)
    (out / "swap_benchmark.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
