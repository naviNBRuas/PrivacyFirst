"""Benchmarks for the context-identifier scan (run 006).

Part 1, SCAN QUALITY (real Tesseract, synthetic scenes): how often are identifier-like items (plate, phone, e-mail,
address) actually covered by a redaction region, how often is ordinary text wrongly redacted, how much blank area is
redacted for nothing, how many 'plate-shaped, unread' flags appear, and the cost per frame. Scenes come from
`contextsynth` (clean rendered fonts, controlled degradation): an optimistic upper bound for real footage.

Part 2, TEMPORAL COVERAGE (simulated scanner): a scanner that finds a ground-truth region with a given miss probability, fed
through the live source and the two-pass planner. This measures the tracking logic (scan cadence, hold, interpolation,
extension), not OCR. Same caveat as the face benchmarks: pipeline behaviour, not real accuracy.

Usage: python -m privacyfirst.bench.contextbench --out DIR [--seeds 4] [--part quality|temporal|both]
"""
from __future__ import annotations
import argparse
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
import cv2
import numpy as np
from ..context import (IDENTIFIER_KINDS, ContextConfig, ContextFinding, ContextKind, ContextScanner, LiveContext,
                       OcrUnavailable, TesseractOcr, build_context_plan)
from ..types import Box
from .contextsynth import VARIANTS, item_mask, make_scene

COVER = 0.8        # an item counts as covered when this fraction of its text area lies inside redaction boxes


def _redaction_mask(findings, cfg: ContextConfig, shape) -> np.ndarray:
    h, w = shape
    m = np.zeros(shape, bool)
    for f in findings:
        if cfg.treatment_for(f.kind) is not None:
            x1, y1, x2, y2 = f.box.expanded(cfg.region_margin, w, h).clamp_int(w, h)
            m[y1:y2, x1:x2] = True
    return m


# ------------------------------------------------------------------------------------------ part 1
CONFIGS = {
    "psm6": dict(passes=((6, 1.0),), shape=False),
    "default": dict(passes=((6, 1.0), (3, 1.0)), shape=False),
    "default+shape": dict(passes=((6, 1.0), (3, 1.0)), shape=True),
    "thorough+shape": dict(passes=((6, 1.0), (3, 1.0), (6, 2.0), (3, 2.0)), shape=True),
}


def run_quality(seeds: int, configs=CONFIGS, variants=VARIANTS) -> dict:
    out: dict = {}
    for cn, c in configs.items():
        cfg = ContextConfig(use_plate_shape=c["shape"])
        sc = ContextScanner(TesseractOcr(passes=c["passes"]), cfg)
        per_var, tot_t, n = {}, 0.0, 0
        for vn, v in variants.items():
            acc = {"cov": {}, "flag": {}, "false_ident": 0, "false_flag": 0, "blank_area": [], "sign_redacted": 0, "signs": 0}
            for sd in range(seeds):
                frame, items = make_scene(1000 + sd, v)
                t = time.time()
                fs = sc.scan_frame(frame)
                tot_t += time.time() - t
                n += 1
                shape = frame.shape[:2]
                red = _redaction_mask(fs, cfg, shape)
                flag = np.zeros(shape, bool)
                for f in fs:
                    if cfg.treatment_for(f.kind) is None:
                        x1, y1, x2, y2 = f.box.clamp_int(shape[1], shape[0])
                        flag[y1:y2, x1:x2] = True
                allgt = np.zeros(shape, bool)
                for it in items:
                    m = item_mask(it, shape)
                    allgt |= m
                    cov = float((red & m).sum() / max(1, m.sum()))
                    acc["cov"].setdefault(it.kind, []).append(cov >= COVER)
                    acc["flag"].setdefault(it.kind, []).append(float(((red | flag) & m).sum() / max(1, m.sum())) >= COVER)
                    if it.kind == "sign":
                        acc["signs"] += 1
                        acc["sign_redacted"] += int(cov >= 0.3)
                near = cv2.dilate(allgt.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool)
                acc["blank_area"].append(float((red & ~near).sum() / red.size))
                boxes = [item.box for item in items]
                for f in fs:
                    on_item = any(f.box.iou(b) > 0.05 or _hit(f.box, b) for b in boxes)
                    if f.kind in IDENTIFIER_KINDS and not on_item:
                        acc["false_ident"] += 1
                    if f.kind == ContextKind.PLATE_SHAPE and not on_item:
                        acc["false_flag"] += 1
            per_var[vn] = {
                "covered": {k: float(np.mean(x)) for k, x in acc["cov"].items()},
                "covered_or_flagged": {k: float(np.mean(x)) for k, x in acc["flag"].items()},
                "identifier_covered": float(np.mean([b for k, x in acc["cov"].items() if k != "sign" for b in x])),
                "false_identifier_findings_per_frame": acc["false_ident"] / seeds,
                "unread_plate_shape_flags_off_item_per_frame": acc["false_flag"] / seeds,
                "blank_area_redacted_pct": 100 * float(np.mean(acc["blank_area"])),
                "signs_wrongly_redacted": acc["sign_redacted"] / max(1, acc["signs"]),
            }
        out[cn] = {"variants": per_var, "sec_per_frame": tot_t / max(1, n),
                   "identifier_covered_mean": float(np.mean([v["identifier_covered"] for v in per_var.values()])),
                   "plate_covered_mean": float(np.mean([v["covered"].get("plate", 0) for v in per_var.values()]))}
    return out


def _hit(a: Box, b: Box) -> bool:
    cx, cy = a.center
    return b.x1 <= cx <= b.x2 and b.y1 <= cy <= b.y2


# ------------------------------------------------------------------------------------------ part 2
N_FRAMES, SIZE = 90, (800, 560)


@dataclass
class Scenario:
    name: str
    visible: range
    x0: float
    vx: float                      # px per frame
    gap: range = range(0)          # frames with the item occluded inside `visible`

    def box(self, i: int) -> Box | None:
        if i not in self.visible or i in self.gap:
            return None
        x = self.x0 + self.vx * (i - self.visible.start)
        return Box(x, 300, x + 150, 340)


def _scenarios(sd: int) -> list[Scenario]:
    """Timing is shifted per seed so the scan cadence is never accidentally aligned with an item's appearance."""
    return [
        Scenario("static", range(0, N_FRAMES), 200, 0),
        Scenario("crossing_8px", range(0, N_FRAMES), 20, 8),
        Scenario("brief_pass_6f", range(30 + 3 * sd, 36 + 3 * sd), 100, 16),
        Scenario("late_appear", range(31 + sd, N_FRAMES), 300, 0),
        Scenario("occluded_4f", range(0, N_FRAMES), 200, 2, gap=range(40 + sd, 44 + sd)),
    ]


SCENARIO_NAMES = [s.name for s in _scenarios(0)]


class SimScanner:
    """Finds the ground-truth box of the current frame with probability 1 - p_miss. Frames carry their own index in pixel [0,0]."""
    name = "sim-scanner"

    def info(self) -> dict:
        return {}

    def __init__(self, sc: Scenario, p_miss: float, seed: int, cfg: ContextConfig):
        self.sc, self.p, self.rng, self.cfg = sc, p_miss, np.random.default_rng(seed), cfg

    def scan_frame(self, frame):
        b = self.sc.box(int(frame[0, 0, 0]))
        if b is None or self.rng.random() < self.p:
            return []
        j = self.rng.normal(0, 2, 4)
        return [ContextFinding(ContextKind.PLATE, Box(b.x1 + j[0], b.y1 + j[1], b.x2 + j[2], b.y2 + j[3]), 0.8)]


def _frame(i: int) -> np.ndarray:
    f = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
    f[0, 0, 0] = i
    return f


def _score(sc: Scenario, per_frame_boxes: list) -> dict:
    gt_frames = [i for i in range(N_FRAMES) if sc.box(i) is not None]
    leak, area, extra = 0, [], 0
    for i in range(N_FRAMES):
        g = sc.box(i)
        regs = per_frame_boxes[i]
        if g is None:
            extra += int(bool(regs))
            continue
        m = np.zeros((SIZE[1], SIZE[0]), bool)
        for r in regs:
            x1, y1, x2, y2 = r.clamp_int(*SIZE)
            m[y1:y2, x1:x2] = True
        gm = np.zeros_like(m)
        x1, y1, x2, y2 = g.clamp_int(*SIZE)
        gm[y1:y2, x1:x2] = True
        leak += int((m & gm).sum() / max(1, gm.sum()) < COVER)
        area.append(sum(r.area for r in regs) / max(1.0, g.area))
    return {"leak_pct": 100 * leak / max(1, len(gt_frames)), "area_factor": float(np.mean(area)) if area else 0.0,
            "extra_frames_pct": 100 * extra / N_FRAMES}


def run_temporal(seeds: int = 8, every=(1, 3, 5, 8), p_miss=(0.0, 0.3), lookahead: int = 4) -> dict:
    out: dict = {}
    for mode in ("live", "plan"):
        for k in every:
            for p in p_miss:
                for ext_name, ext in (("default", -1), ("none", 0)):
                    if mode == "live" and ext_name == "none":
                        continue
                    cfg = ContextConfig(scan_every=k, extend_frames=ext)
                    row = {}
                    for si, name in enumerate(SCENARIO_NAMES):
                        rs = []
                        for sd in range(seeds):
                            sc = _scenarios(sd)[si]
                            scn = SimScanner(sc, p, sd, cfg)
                            boxes = [[] for _ in range(N_FRAMES)]
                            if mode == "live":
                                lc = LiveContext(scn)
                                for i in range(N_FRAMES):
                                    cf = lc.frame(i, _frame(i))
                                    for r in cf.regions:
                                        boxes[i].append(r.box)
                                        if r.cid in cf.new_ids:                    # backfill into the lookahead, as the pipeline does
                                            for back in range(1, lookahead + 1):
                                                if i - back >= 0:
                                                    boxes[i - back].append(r.box)
                            else:
                                res = {i: scn.scan_frame(_frame(i)) for i in range(0, N_FRAMES, k)}
                                plan = build_context_plan(res, N_FRAMES, SIZE, cfg, scn.name)
                                for i in range(N_FRAMES):
                                    boxes[i] = [r.box for r in plan.regions[i]]
                            rs.append(_score(sc, boxes))
                        row[name] = {m: float(np.mean([r[m] for r in rs])) for m in rs[0]}
                    out[f"{mode}|every={k}|p_miss={p}|extend={ext_name}"] = row
    return out


# ------------------------------------------------------------------------------------------ report
def _md(q: dict | None, t: dict | None, seeds: int) -> str:
    L = ["# Context-identifier scan benchmark (run 006)", "",
         "SYNTHETIC. Part 1 uses clean rendered fonts (Liberation/DejaVu) on invented plates, numbers and addresses with controlled "
         "degradation; real plates, signs, cameras, perspective, motion blur and non-English text are NOT represented, so treat every "
         "number as an optimistic upper bound. Part 2 uses a simulated scanner and measures tracking logic only.", ""]
    if q:
        L += [f"## Part 1: scan quality (real Tesseract, {seeds} scenes per variant, 5 items per scene)", "",
              "'covered' = at least 80% of the item's text area lies inside a redaction region the pipeline would apply.", "",
              "| config | sec/frame (1 core) | identifiers covered | plates covered |", "|---|---|---|---|"]
        for cn, r in q.items():
            L.append(f"| {cn} | {r['sec_per_frame']:.2f} | {100 * r['identifier_covered_mean']:.0f}% | {100 * r['plate_covered_mean']:.0f}% |")
        for cn, r in q.items():
            L += ["", f"### {cn}", "", "| variant | plate | phone | e-mail | address | sign flagged/covered | false ident. findings/frame | "
                  "unread-shape flags off-item/frame | blank area redacted | signs wrongly redacted |", "|---|---|---|---|---|---|---|---|---|---|"]
            for vn, v in r["variants"].items():
                c, cf = v["covered"], v["covered_or_flagged"]
                L.append(f"| {vn} | {100 * c.get('plate', 0):.0f}% | {100 * c.get('phone', 0):.0f}% | {100 * c.get('email', 0):.0f}% | "
                         f"{100 * c.get('address', 0):.0f}% | {100 * cf.get('sign', 0):.0f}% | {v['false_identifier_findings_per_frame']:.2f} | "
                         f"{v['unread_plate_shape_flags_off_item_per_frame']:.2f} | {v['blank_area_redacted_pct']:.2f}% | "
                         f"{100 * v['signs_wrongly_redacted']:.0f}% |")
    if t:
        L += ["", "## Part 2: temporal coverage with a simulated scanner (90 frames, 800x560)", "",
              "leak% = share of frames where the item is visible but less than 80% covered; area = redacted area / item area while visible; "
              "extra = share of frames redacting while the item is NOT visible (tails). `extend=none` turns off the two-pass extension.", ""]
        names = SCENARIO_NAMES
        L += ["| mode | every | p_miss | extend | " + " | ".join(f"{n} leak% / area" for n in names) + " | extra% (mean) |",
              "|---|---|---|---|" + "---|" * (len(names) + 1)]
        for key, row in t.items():
            mode, ev, pm, ex = [p.split("=")[-1] if "=" in p else p for p in key.split("|")]
            L.append(f"| {mode} | {ev} | {pm} | {ex} | " + " | ".join(f"{row[n]['leak_pct']:.1f} / {row[n]['area_factor']:.1f}" for n in names)
                     + f" | {np.mean([row[n]['extra_frames_pct'] for n in names]):.1f} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="privacyfirst.bench.contextbench")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--part", choices=["quality", "temporal", "both"], default="both")
    ap.add_argument("--configs", default=",".join(CONFIGS), help="comma list of quality configs")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    q = t = None
    if a.part in ("quality", "both"):
        try:
            TesseractOcr.check()
        except OcrUnavailable as e:
            print(f"quality part needs tesseract: {e}")
            return 2
        q = run_quality(a.seeds, {k: CONFIGS[k] for k in a.configs.split(",")})
    if a.part in ("temporal", "both"):
        t = run_temporal(max(4, a.seeds))
    (out / "context_benchmark.json").write_text(json.dumps({"quality": q, "temporal": t, "seeds": a.seeds}, indent=1))
    (out / "context_benchmark.md").write_text(_md(q, t, a.seeds))
    print(_md(q, t, a.seeds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
