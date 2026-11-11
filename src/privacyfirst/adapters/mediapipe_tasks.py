"""MediaPipe BlazeFace via the Tasks API (Apache-2.0 code; verify the model's terms).
UNTESTED against a real model file in this repo's CI sandbox: run docs/phase0 smoke checks locally."""
from __future__ import annotations
import cv2
import numpy as np
from . import resolve_model
from ..types import Box, Detection

FILENAME = "blaze_face_short_range.tflite"


class MediaPipeFaceDetector:
    name = "mediapipe-blazeface-short-range"

    def __init__(self, model_path=None, min_conf: float = 0.2):
        path = resolve_model(model_path, FILENAME)          # raises FileNotFoundError with instructions
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        self._mp = mp
        opts = vision.FaceDetectorOptions(base_options=mpp.BaseOptions(model_asset_path=str(path)),
                                          min_detection_confidence=min_conf)
        self._det = vision.FaceDetector.create_from_options(opts)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self._det.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb))
        out = []
        for d in res.detections:
            b = d.bounding_box
            out.append(Detection(Box(b.origin_x, b.origin_y, b.origin_x + b.width, b.origin_y + b.height),
                                 float(d.categories[0].score)))
        return out
