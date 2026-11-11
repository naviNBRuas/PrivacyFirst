"""Deterministic synthetic clips with per-frame ground truth. No real people, no media files."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Callable
import cv2
import numpy as np
from ..types import Box

W, H = 192, 144

SCENARIOS = ["baseline", "tiny_faces", "low_light", "motion_blur", "occlusion", "crowd",
             "late_appearance", "late_long", "edge_entry", "erratic_motion", "exit_reenter"]


@dataclass
class GTFace:
    id: int
    box: Box              # clipped to frame
    visible: bool         # False when mostly outside the frame or occluded: excluded from leak metrics
    visible_frac: float = 1.0


@dataclass
class DetectorProfile:
    """Failure-mode parameters consumed by SimulatedDetector (assumptions, not measurements)."""
    p_enter_miss: float = 0.02      # per-frame chance a detected face starts a miss burst
    mean_burst: float = 3.0         # mean burst length (frames), geometric
    min_visible_frac: float = 0.6   # below this, the detector never fires
    min_size: float = 14.0          # faces smaller than this (px) are never detected
    jitter_px: float = 1.5
    fp_per_frame: float = 0.02      # expected false positives per frame
    blind_until: int = 0            # detector cannot see any face before this frame
    base_conf: float = 0.88


@dataclass
class Clip:
    name: str
    scenario: str
    seed: int
    n_frames: int
    gt: list[list[GTFace]]
    render: Callable[[int], np.ndarray]
    profile: DetectorProfile
    notes: str = ""

    def frames(self):
        for i in range(self.n_frames):
            yield self.render(i)


Traj = Callable[[int], tuple[float, float, float]]     # t -> (cx, cy, half_size)


def _clip_box(cx, cy, s) -> tuple[Box, float]:
    full = Box(cx - s, cy - s * 1.2, cx + s, cy + s * 1.2)
    x1, y1, x2, y2 = max(0, full.x1), max(0, full.y1), min(W, full.x2), min(H, full.y2)
    vis = Box(x1, y1, max(x1, x2), max(y1, y2))
    frac = vis.area / full.area if full.area > 0 else 0.0
    return vis, frac


def _draw_face(img, cx, cy, s, tone):
    rx, ry = max(2, int(s)), max(2, int(s * 1.2))
    cv2.ellipse(img, (int(cx), int(cy)), (rx, ry), 0, 0, 360, tone, -1)
    for dx in (-rx // 2, rx // 2):
        cv2.circle(img, (int(cx) + dx, int(cy) - ry // 4), max(1, rx // 6), (40, 30, 30), -1)


def _build(name, scenario, seed, n, trajs: list[Traj], profile: DetectorProfile, *,
           brightness=1.0, blur=0, occluder: tuple[int, int, int, int] | None = None,
           occl_frames: range | None = None, notes="") -> Clip:
    rng = np.random.default_rng(seed)
    tones = [(150, 180, 230), (120, 150, 200), (100, 130, 180), (170, 200, 240)]
    bg = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        bg[y, :] = (50 + y // 3, 80 + y // 5, 100)
    noise = rng.integers(0, 12, (H, W, 3), dtype=np.uint8)
    bg = cv2.add(bg, noise)
    gt: list[list[GTFace]] = []
    for t in range(n):
        row = []
        for i, tr in enumerate(trajs):
            cx, cy, s = tr(t)
            box, frac = _clip_box(cx, cy, s)
            vis = frac >= 0.3
            if occluder and occl_frames is not None and t in occl_frames:
                ox1, oy1, ox2, oy2 = occluder
                inter = Box(max(box.x1, ox1), max(box.y1, oy1), min(box.x2, ox2), min(box.y2, oy2))
                if box.area > 0 and inter.area / box.area > 0.7:
                    vis = False
                frac *= 1 - (inter.area / box.area if box.area > 0 else 0)
            row.append(GTFace(i, box, vis, frac))
        gt.append(row)

    def render(t: int) -> np.ndarray:
        img = bg.copy()
        for i, tr in enumerate(trajs):
            cx, cy, s = tr(t)
            _draw_face(img, cx, cy, s, tones[i % len(tones)])
        if occluder and occl_frames is not None and t in occl_frames:
            x1, y1, x2, y2 = occluder
            img[y1:y2, x1:x2] = (30, 30, 30)
        if blur:
            k = np.zeros((blur, blur), np.float32); k[blur // 2, :] = 1.0 / blur
            img = cv2.filter2D(img, -1, k)
        if brightness != 1.0:
            img = np.clip(img.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
        return img

    return Clip(name, scenario, seed, n, gt, render, profile, notes)


def make_clip(scenario: str, seed: int = 0, n_frames: int = 120) -> Clip:
    r = np.random.default_rng(seed + 1000)
    ph = lambda: float(r.uniform(0, 6.28))
    nm = f"{scenario}-s{seed}"

    def wander(cx0, cy0, ax, ay, s, speed=1.0, p=0.0):
        return lambda t: (cx0 + ax * math.sin(speed * t / 17 + p), cy0 + ay * math.sin(speed * t / 11 + p * 1.7), s)

    if scenario == "baseline":
        return _build(nm, scenario, seed, n_frames, [wander(60, 70, 40, 15, 20, 1, ph()), wander(130, 70, 35, 15, 17, 1, ph())],
                      DetectorProfile(), notes="two moderate faces, mild dropouts")
    if scenario == "tiny_faces":
        return _build(nm, scenario, seed, n_frames, [wander(40 + 40 * i, 50 + 25 * (i % 2), 15, 10, 5 + i, 1, ph()) for i in range(3)],
                      DetectorProfile(p_enter_miss=0.12, mean_burst=6, min_size=14, jitter_px=2.0),
                      notes="faces ~5-7 px half-size; detector often below its min size")
    if scenario == "low_light":
        return _build(nm, scenario, seed, n_frames, [wander(60, 70, 40, 15, 20, 1, ph()), wander(130, 70, 35, 15, 17, 1, ph())],
                      DetectorProfile(p_enter_miss=0.20, mean_burst=8, base_conf=0.55), brightness=0.28,
                      notes="dark frames, long correlated miss bursts, low confidence")
    if scenario == "motion_blur":
        return _build(nm, scenario, seed, n_frames, [wander(96, 70, 80, 20, 20, 4.0, ph()), wander(96, 80, 70, 25, 18, 3.4, ph())],
                      DetectorProfile(p_enter_miss=0.12, mean_burst=4, jitter_px=4.0), blur=9,
                      notes="fast motion with horizontal blur")
    if scenario == "occlusion":
        return _build(nm, scenario, seed, n_frames, [lambda t: (30 + 1.4 * t, 72, 18), wander(150, 60, 20, 10, 17, 1, ph())],
                      DetectorProfile(p_enter_miss=0.03), occluder=(80, 30, 110, 120), occl_frames=range(0, n_frames),
                      notes="face passes behind a pillar")
    if scenario == "crowd":
        trajs = [wander(20 + 21 * i, 40 + 14 * (i % 5), 10, 8, 11 + (i % 3), 1, ph()) for i in range(8)]
        return _build(nm, scenario, seed, n_frames, trajs, DetectorProfile(p_enter_miss=0.05, mean_burst=4, jitter_px=2.5),
                      notes="8 overlapping faces")
    if scenario == "late_appearance":
        return _build(nm, scenario, seed, n_frames, [wander(70, 70, 30, 10, 20, 1, ph()), wander(130, 75, 20, 10, 18, 1, ph())],
                      DetectorProfile(blind_until=12), notes="detector blind for the first 12 frames (e.g. face turned away)")
    if scenario == "late_long":
        return _build(nm, scenario, seed, n_frames, [wander(70, 70, 30, 10, 20, 1, ph()), wander(130, 75, 20, 10, 18, 1, ph())],
                      DetectorProfile(blind_until=30), notes="detector blind for the first 30 frames: longer than two-pass back_extend (16)")
    if scenario == "edge_entry":
        return _build(nm, scenario, seed, n_frames, [lambda t: (-20 + 4.0 * t, 70, 20), lambda t: (W + 20 - 3.5 * t, 95, 18)],
                      DetectorProfile(min_visible_frac=0.6), notes="faces enter from the frame edges (partial faces)")
    if scenario == "erratic_motion":
        def zig(c0, y0, s, per, amp):
            return lambda t: (c0 + amp * (abs(((t % (2 * per)) - per)) / per - 0.5) * 2, y0 + 12 * math.sin(t / 3), s)
        return _build(nm, scenario, seed, n_frames, [zig(60, 70, 19, 14, 45), zig(135, 80, 17, 11, 35)],
                      DetectorProfile(p_enter_miss=0.08, mean_burst=4, jitter_px=3.0), notes="sudden direction reversals every ~11-14 frames")
    if scenario == "exit_reenter":
        def leaves(t):
            u = t % 80
            x = 40 + 6 * u if u < 25 else (-60 if u < 55 else -60 + 8 * (u - 55))
            return (x, 70, 19)
        return _build(nm, scenario, seed, n_frames, [leaves, wander(140, 60, 15, 10, 17, 1, ph())], DetectorProfile(),
                      notes="face leaves the frame and returns later (track ID continuity)")
    raise ValueError(f"unknown scenario {scenario}")
