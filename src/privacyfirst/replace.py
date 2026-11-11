"""FaceReplacer protocol and a deterministic NON-AI stub backend.

The stub draws a flat cartoon face in the assigned identity's colors. It exists so every gate around a
real swap model (assignment, smoothing, blending, verification, demotion) is testable without weights.
It does NOT preserve expression, gaze, or pose, and must never be presented as an AI face change.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol
import cv2
import numpy as np
from .blend import ellipse_head_mask
from .identity import Identity
from .types import Box


@dataclass
class Replacement:
    head_box: Box                 # frame-clamped integer box the patch/mask cover
    patch: np.ndarray             # HxWx3 uint8, aligned to head_box
    mask: np.ndarray              # HxW float32 0-1
    health: float                 # 0-1 replacer self-assessment (pose in range, mask quality, occlusion)
    notes: list[str] = field(default_factory=list)


class FaceReplacer(Protocol):
    name: str
    is_stub: bool
    def replace(self, frame: np.ndarray, track, head_box: Box, identity: Identity, frame_idx: int) -> Replacement: ...


class StubReplacer:
    name = "stub-replacer (NOT AI)"
    is_stub = True

    def __init__(self, health_fn: Optional[Callable[[int, int, Box], float]] = None,
                 error_fn: Optional[Callable[[int, int], bool]] = None, min_px: int = 24):
        self.health_fn, self.error_fn, self.min_px = health_fn, error_fn, min_px

    def replace(self, frame, track, head_box, identity, frame_idx):
        if self.error_fn and self.error_fn(track.id, frame_idx):
            raise RuntimeError("injected replacer failure")
        H, W = frame.shape[:2]
        x1, y1, x2, y2 = head_box.clamp_int(W, H)
        ww, hh = max(1, x2 - x1), max(1, y2 - y1)
        ap = identity.appearance
        patch = np.empty((hh, ww, 3), np.uint8)
        patch[:] = tuple(ap["skin"])
        cx = ww // 2
        hair = tuple(ap["hair"])
        cv2.ellipse(patch, (cx, int(hh * 0.36)), (int(ww * 0.47), int(hh * 0.34)), 0, 180, 360, hair, -1)
        if ap.get("hair_style", 0) == 1:
            cv2.rectangle(patch, (int(ww * 0.05), int(hh * 0.30)), (int(ww * 0.95), int(hh * 0.40)), hair, -1)
        ex, ey, er = (int(ww * 0.30), int(ww * 0.70)), int(hh * 0.46), max(1, int(ww * 0.07))
        for x in ex:
            cv2.ellipse(patch, (x, ey), (er + 1, max(1, er - 1)), 0, 0, 360, (240, 240, 240), -1)
            cv2.circle(patch, (x, ey), max(1, er // 2), tuple(ap["eye"]), -1)
            cv2.line(patch, (x - er, ey - er - 2), (x + er, ey - er - 1), hair, 1)
        cv2.line(patch, (cx, int(hh * 0.50)), (cx - max(1, ww // 20), int(hh * 0.62)), tuple(int(c * 0.8) for c in ap["skin"]), 1)
        cv2.ellipse(patch, (cx, int(hh * 0.72)), (max(1, int(ww * 0.14)), max(1, int(hh * 0.05))), 0, 0, 180, tuple(ap["lip"]), 2)
        mask = ellipse_head_mask(hh, ww)
        health = (self.health_fn(track.id, frame_idx, head_box) if self.health_fn
                  else min(1.0, min(ww, hh) / self.min_px))
        return Replacement(Box(x1, y1, x2, y2), patch, mask, float(health), ["stub"])
