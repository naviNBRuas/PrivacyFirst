from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Treatment(str, Enum):
    """Ordered from weakest to strongest. Fallbacks only ever move *up* this list."""
    SWAP = "swap"        # reserved for Phase 2, never emitted in Phase 1
    BLUR = "blur"
    MOSAIC = "mosaic"
    BLOCK = "block"      # solid fill


STRENGTH = {Treatment.SWAP: 0, Treatment.BLUR: 1, Treatment.MOSAIC: 2, Treatment.BLOCK: 3}


def stronger(a: Treatment, b: Treatment) -> Treatment:
    return a if STRENGTH[a] >= STRENGTH[b] else b


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def h(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def iou(self, o: "Box") -> float:
        ix1, iy1 = max(self.x1, o.x1), max(self.y1, o.y1)
        ix2, iy2 = min(self.x2, o.x2), min(self.y2, o.y2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = self.area + o.area - inter
        return inter / union if union > 0 else 0.0

    def shifted(self, dx: float, dy: float) -> "Box":
        return Box(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def expanded(self, margin: float, w: int, h: int) -> "Box":
        """Grow by `margin` (fraction of size) per side, clamped to the frame."""
        mx, my = self.w * margin, self.h * margin
        return Box(max(0, self.x1 - mx), max(0, self.y1 - my),
                   min(w, self.x2 + mx), min(h, self.y2 + my))

    def clamp_int(self, w: int, h: int) -> tuple[int, int, int, int]:
        return (int(max(0, min(w, round(self.x1)))), int(max(0, min(h, round(self.y1)))),
                int(max(0, min(w, round(self.x2)))), int(max(0, min(h, round(self.y2)))))


@dataclass(frozen=True)
class Detection:
    box: Box
    conf: float
    # Optional model output: estimated probability the person is under 18.
    # None means "unknown", and the policy engine treats unknown as minor-risk.
    minor_prob: Optional[float] = None


@dataclass
class Decision:
    treatment: Treatment
    reasons: list[str]
