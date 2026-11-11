"""Temporal stability helpers: One-Euro filter, patch EMA, and a flicker metric."""
from __future__ import annotations
import math
from typing import Optional, Sequence
import cv2
import numpy as np


class OneEuro:
    """One-Euro filter (Casiez et al.): low lag when moving fast, strong smoothing when still."""
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.05, d_cutoff: float = 1.0, freq: float = 30.0):
        self.min_cutoff, self.beta, self.d_cutoff, self.freq = min_cutoff, beta, d_cutoff, freq
        self._x: Optional[float] = None
        self._dx = 0.0

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau * self.freq)

    def __call__(self, x: float) -> float:
        if self._x is None:
            self._x = x
            return x
        dx = (x - self._x) * self.freq
        a_d = self._alpha(self.d_cutoff)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff)
        self._x = a * x + (1 - a) * self._x
        return self._x


class PatchStabilizer:
    """EMA over aligned replacement patches. Resets when the patch shape changes."""
    def __init__(self, alpha: float = 0.6):
        self.alpha = alpha
        self._prev: Optional[np.ndarray] = None

    def update(self, patch: np.ndarray) -> np.ndarray:
        if self._prev is None or self._prev.shape != patch.shape:
            self._prev = patch.astype(np.float32)
        else:
            self._prev = self.alpha * patch.astype(np.float32) + (1 - self.alpha) * self._prev
        return np.clip(self._prev, 0, 255).astype(np.uint8)

    def reset(self) -> None:
        self._prev = None


def flicker_score(patches: Sequence[np.ndarray], size: int = 32) -> float:
    """Mean absolute frame-to-frame change of ALIGNED patches (0-255 scale). Lower is steadier."""
    if len(patches) < 2:
        return 0.0
    g = [cv2.resize(cv2.cvtColor(p, cv2.COLOR_BGR2GRAY), (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
         for p in patches]
    return float(np.mean([np.abs(a - b).mean() for a, b in zip(g, g[1:])]))
