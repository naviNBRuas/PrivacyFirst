import numpy as np
import pytest
from privacyfirst.types import Box, Detection

W, H = 160, 120


def make_frame(seed=0, face=Box(60, 40, 100, 80)):
    """Noisy grey frame; the 'face' region is high-variance texture so redaction is measurable."""
    rng = np.random.default_rng(seed)
    f = np.full((H, W, 3), 90, np.uint8)
    x1, y1, x2, y2 = (int(v) for v in (face.x1, face.y1, face.x2, face.y2))
    f[y1:y2, x1:x2] = rng.integers(0, 255, (y2 - y1, x2 - x1, 3), dtype=np.uint8)
    return f


def region_std(frame, box):
    x1, y1, x2, y2 = (int(v) for v in (box.x1, box.y1, box.x2, box.y2))
    return float(frame[y1:y2, x1:x2].astype(np.float32).std())


@pytest.fixture
def face():
    return Box(60, 40, 100, 80)


def det(box, conf=0.9, minor=None):
    return Detection(box, conf, minor)
