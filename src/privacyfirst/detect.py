"""Detector interface plus Phase 1 placeholder detectors.

The OpenCV Haar detector is a PLUMBING PLACEHOLDER so the pipeline runs end to
end with no model downloads. It is far weaker than the Phase 0 candidates
(BlazeFace / YuNet) and must not be used to make real privacy claims.
"""
from __future__ import annotations
from typing import Protocol, Sequence
import numpy as np
from .types import Box, Detection


class Detector(Protocol):
    name: str
    def detect(self, frame: np.ndarray) -> Sequence[Detection]: ...


class HaarDetector:
    """Frontal + profile Haar cascades at a deliberately permissive setting."""
    name = "opencv-haar (placeholder)"

    def __init__(self) -> None:
        import cv2
        self._cv2 = cv2
        base = cv2.data.haarcascades
        self._frontal = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
        self._profile = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        cv2 = self._cv2
        gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        out: list[Detection] = []
        for casc in (self._frontal, self._profile):
            # minNeighbors=2 is permissive on purpose: extra boxes are cheap, misses are not.
            rects = casc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=2, minSize=(24, 24))
            for (x, y, w, h) in rects:
                out.append(Detection(Box(x, y, x + w, y + h), conf=0.6))
        return out


class ScriptedDetector:
    """Test/demo detector driven by a per-frame script (supports dropouts)."""
    name = "scripted"

    def __init__(self, script: dict[int, list[Detection]]):
        self.script = script
        self._i = -1

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self._i += 1
        return list(self.script.get(self._i, []))
