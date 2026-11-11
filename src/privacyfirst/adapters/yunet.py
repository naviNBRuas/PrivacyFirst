"""YuNet via OpenCV's FaceDetectorYN (MIT; verify the model's terms).
UNTESTED against a real model file in this repo's CI sandbox: run docs/phase0 smoke checks locally."""
from __future__ import annotations
import cv2
import numpy as np
from . import resolve_model
from ..types import Box, Detection

FILENAME = "face_detection_yunet_2023mar.onnx"


class YuNetDetector:
    name = "yunet-2023mar"

    def __init__(self, model_path=None, min_conf: float = 0.3):
        path = resolve_model(model_path, FILENAME)
        self._det = cv2.FaceDetectorYN.create(str(path), "", (320, 320), score_threshold=min_conf,
                                              nms_threshold=0.3, top_k=500)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(frame)
        out = []
        for f in (faces if faces is not None else []):
            x, y, bw, bh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
            out.append(Detection(Box(x, y, x + bw, y + bh), score))
        return out
