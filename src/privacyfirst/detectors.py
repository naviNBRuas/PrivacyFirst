"""Detector factory shared by the CLI and the measurement tool. Real detectors need model files (docs/phase0/MODEL_SETUP.md)."""
from __future__ import annotations
from typing import Optional


def make_detector(name: str, model_dir: Optional[str] = None):
    if model_dir:
        import os
        os.environ["PRIVACYFIRST_MODEL_DIR"] = model_dir
    if name == "haar":
        from .detect import HaarDetector
        return HaarDetector()
    if name == "yunet":
        from .adapters.yunet import YuNetDetector
        return YuNetDetector()
    if name == "mediapipe":
        from .adapters.mediapipe_tasks import MediaPipeFaceDetector
        return MediaPipeFaceDetector()
    raise ValueError(f"unknown detector {name!r}")
