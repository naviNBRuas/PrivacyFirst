"""Head mask, color matching, grain matching, and feathered compositing."""
from __future__ import annotations
import cv2
import numpy as np
from .types import Box


def ellipse_head_mask(h: int, w: int, feather: float = 0.18) -> np.ndarray:
    """Soft elliptical head mask (float32 0-1). A segmentation model replaces this in Phase 2."""
    m = np.zeros((h, w), np.float32)
    cv2.ellipse(m, (w // 2, h // 2), (max(1, int(w * 0.46)), max(1, int(h * 0.48))), 0, 0, 360, 1.0, -1)
    k = max(3, int(min(h, w) * feather)) | 1
    return np.clip(cv2.GaussianBlur(m, (k, k), 0), 0, 1)


def match_color(patch: np.ndarray, mask: np.ndarray, ref: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Reinhard-style LAB mean/std transfer from the original region onto the patch (relighting proxy)."""
    sel = mask > 0.5
    if strength <= 0 or sel.sum() < 4 or ref.shape != patch.shape:
        return patch
    lp = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)
    lr = cv2.cvtColor(ref, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = lp.copy()
    for c in range(3):
        mp, sp = lp[..., c][sel].mean(), lp[..., c][sel].std()
        mr, sr = lr[..., c][sel].mean(), lr[..., c][sel].std()
        scale = float(np.clip(sr / (sp + 1e-3), 0.5, 2.0))
        out[..., c] = lp[..., c] * (1 - strength) + ((lp[..., c] - mp) * scale + mr) * strength
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def noise_sigma(ref: np.ndarray) -> float:
    g = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    return float(min(6.0, 1.4826 * np.median(np.abs(lap - np.median(lap))) / 4.0))


def add_grain(patch: np.ndarray, ref: np.ndarray, rng: np.random.Generator, gain: float = 1.0) -> np.ndarray:
    s = noise_sigma(ref) * gain
    if s <= 0.05:
        return patch
    return np.clip(patch.astype(np.float32) + rng.normal(0, s, patch.shape), 0, 255).astype(np.uint8)


def composite(frame: np.ndarray, head_box: Box, patch: np.ndarray, mask: np.ndarray, ref_frame: np.ndarray,
              rng: np.random.Generator, color_strength: float = 0.6, grain: float = 1.0) -> None:
    """In place: blend `patch` into `frame` over `head_box`, using `ref_frame` (the unmodified frame) for stats."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = head_box.clamp_int(w, h)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    size = (x2 - x1, y2 - y1)
    if patch.shape[1::-1] != size:
        patch = cv2.resize(patch, size)
        mask = cv2.resize(mask, size)
    ref = ref_frame[y1:y2, x1:x2]
    p = add_grain(match_color(patch, mask, ref, color_strength), ref, rng, grain)
    a = mask[..., None]
    frame[y1:y2, x1:x2] = np.clip(a * p.astype(np.float32) + (1 - a) * frame[y1:y2, x1:x2].astype(np.float32), 0, 255).astype(np.uint8)
