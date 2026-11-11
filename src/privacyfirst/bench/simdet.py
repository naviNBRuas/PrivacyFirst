"""Failure-mode detector simulator. Replays clip ground truth through an assumed miss process.

Misses are a two-state Markov chain per face (bursty, like real detectors), plus hard limits
(visible fraction, minimum size, blind period), box jitter, and false positives.
"""
from __future__ import annotations
import numpy as np
from ..types import Box, Detection
from .synth import Clip, W, H


class SimulatedDetector:
    name = "simulated (benchmark only)"

    def __init__(self, clip: Clip, seed: int = 0):
        self.clip = clip
        self.p = clip.profile
        self.rng = np.random.default_rng(seed * 7919 + clip.seed)
        self.i = -1
        self.missing: dict[int, int] = {}      # face id -> remaining miss frames

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self.i += 1
        p, rng = self.p, self.rng
        out: list[Detection] = []
        if self.i >= self.p.blind_until:
            for g in self.clip.gt[self.i]:
                if not g.visible or g.visible_frac < p.min_visible_frac or min(g.box.w, g.box.h) < p.min_size * 0.8:
                    continue
                left = self.missing.get(g.id, 0)
                if left > 0:
                    self.missing[g.id] = left - 1
                    continue
                if rng.random() < p.p_enter_miss:
                    self.missing[g.id] = int(rng.geometric(1.0 / max(1.0, p.mean_burst))) - 1
                    continue
                j = rng.normal(0, p.jitter_px, 4)
                b = Box(g.box.x1 + j[0], g.box.y1 + j[1], g.box.x2 + j[2], g.box.y2 + j[3])
                if b.area > 4:
                    out.append(Detection(b, float(np.clip(rng.normal(p.base_conf, 0.06), 0.05, 0.99))))
        while rng.random() < p.fp_per_frame:
            cx, cy, s = rng.uniform(10, W - 10), rng.uniform(10, H - 10), rng.uniform(8, 18)
            out.append(Detection(Box(cx - s, cy - s, cx + s, cy + s), float(rng.uniform(0.3, 0.6))))
            break
        return out
