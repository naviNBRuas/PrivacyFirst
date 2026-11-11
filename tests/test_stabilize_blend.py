import numpy as np
from privacyfirst.blend import composite, ellipse_head_mask, match_color
from privacyfirst.stabilize import OneEuro, PatchStabilizer, flicker_score
from privacyfirst.types import Box


def test_one_euro_reduces_jitter_but_follows_motion():
    rng = np.random.default_rng(0)
    truth = np.full(200, 50.0)
    noisy = truth + rng.normal(0, 2.0, 200)
    f = OneEuro()
    sm = np.array([f(v) for v in noisy])
    assert sm[50:].std() < noisy[50:].std() * 0.7
    f2 = OneEuro(); ramp = np.linspace(0, 100, 100)
    out = np.array([f2(v) for v in ramp])
    assert abs(out[-1] - ramp[-1]) < 10                        # low lag on sustained motion


def test_flicker_metric_and_patch_ema():
    rng = np.random.default_rng(1)
    base = np.full((40, 40, 3), 120, np.uint8)
    steady = [base.copy() for _ in range(10)]
    noisy = [np.clip(base + rng.normal(0, 12, base.shape), 0, 255).astype(np.uint8) for _ in range(10)]
    alt = [np.full((40, 40, 3), 60 if i % 2 else 190, np.uint8) for i in range(10)]    # identity flipping
    assert flicker_score(steady) < 0.01
    assert flicker_score(alt) > 50
    stab = PatchStabilizer(alpha=0.4)
    smoothed = [stab.update(p) for p in noisy]
    assert flicker_score(smoothed) < flicker_score(noisy) * 0.7


def test_head_mask_shape_and_range():
    m = ellipse_head_mask(60, 50)
    assert m.shape == (60, 50) and m.dtype == np.float32 and 0 <= m.min() and m.max() <= 1
    assert m[30, 25] > 0.95 and m[0, 0] < 0.05


def test_composite_only_touches_head_box_and_mask_support():
    rng = np.random.default_rng(0)
    frame = np.full((100, 120, 3), 90, np.uint8)
    ref = frame.copy()
    box = Box(30, 20, 90, 80)
    mask = ellipse_head_mask(60, 60)
    patch = np.full((60, 60, 3), (40, 200, 60), np.uint8)
    composite(frame, box, patch, mask, ref, rng, color_strength=0.0, grain=0.0)
    assert (frame[:20] == ref[:20]).all() and (frame[:, :30] == ref[:, :30]).all() and (frame[80:] == ref[80:]).all()
    assert (frame[20:80, 30:90][mask < 1e-6] == 90).all()      # outside mask support: unchanged
    assert tuple(frame[50, 60]) == (40, 200, 60)               # mask centre = patch exactly when no colour match


def test_match_color_moves_toward_reference():
    mask = np.ones((20, 20), np.float32)
    patch = np.full((20, 20, 3), (200, 200, 200), np.uint8)
    ref = np.full((20, 20, 3), (40, 60, 90), np.uint8)
    out = match_color(patch, mask, ref, strength=0.7)
    assert abs(float(out.mean()) - float(ref.mean())) < abs(float(patch.mean()) - float(ref.mean()))
