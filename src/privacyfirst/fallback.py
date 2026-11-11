"""Destructive region treatments. numpy + OpenCV only, no models."""
from __future__ import annotations
import cv2
import numpy as np
from .types import Box, Treatment

MOSAIC_BLOCKS = 6        # blocks across the longer side, so a face is ~6x6 colour cells
BLUR_SIGMA_FRAC = 0.33   # sigma as a fraction of the longer side: heavy on purpose


def apply_treatment(frame: np.ndarray, box: Box, treatment: Treatment) -> None:
    """In place. SWAP is not implemented in Phase 1 and degrades to BLOCK, never to nothing."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box.clamp_int(w, h)
    if x2 <= x1 or y2 <= y1:
        return
    roi = frame[y1:y2, x1:x2]
    if treatment == Treatment.BLUR:
        sigma = max(2.0, BLUR_SIGMA_FRAC * max(x2 - x1, y2 - y1))
        k = int(sigma * 6) | 1
        # Two passes: a single Gaussian is the weakest option against deblurring.
        roi[:] = cv2.GaussianBlur(cv2.GaussianBlur(roi, (k, k), sigma), (k, k), sigma)
    elif treatment == Treatment.MOSAIC:
        rh, rw = roi.shape[:2]
        s = MOSAIC_BLOCKS / max(rh, rw)
        small = cv2.resize(roi, (max(1, int(rw * s)), max(1, int(rh * s))), interpolation=cv2.INTER_AREA)
        roi[:] = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
    else:  # BLOCK, and SWAP (unimplemented) fails closed
        roi[:] = 0


def apply_full_frame(frame: np.ndarray, treatment: Treatment) -> None:
    h, w = frame.shape[:2]
    apply_treatment(frame, Box(0, 0, w, h), treatment)
