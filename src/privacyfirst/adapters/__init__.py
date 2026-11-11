"""Adapters that put real face-detection models behind the `Detector` protocol.

Model files are NOT bundled (size, license review). Put them in a folder and set
PRIVACYFIRST_MODEL_DIR, or pass an explicit path. See docs/phase0/MODEL_SETUP.md.
"""
from __future__ import annotations
import os
from pathlib import Path

ENV_VAR = "PRIVACYFIRST_MODEL_DIR"


def resolve_model(path: str | os.PathLike | None, filename: str) -> Path:
    cands = []
    if path:
        cands.append(Path(path))
    if os.environ.get(ENV_VAR):
        cands.append(Path(os.environ[ENV_VAR]) / filename)
    for c in cands:
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"Model file '{filename}' not found (looked in: {[str(c) for c in cands] or 'nothing configured'}). "
        f"Download it per docs/phase0/MODEL_SETUP.md and pass its path or set {ENV_VAR}.")
