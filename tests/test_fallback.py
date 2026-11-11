import numpy as np
from privacyfirst.fallback import apply_treatment, apply_full_frame
from privacyfirst.types import Box, Treatment
from conftest import make_frame, region_std


def test_block_zeroes_region_only(face):
    f = make_frame(); orig = f.copy()
    apply_treatment(f, face, Treatment.BLOCK)
    assert f[40:80, 60:100].max() == 0
    assert (f[:40] == orig[:40]).all()


def test_mosaic_destroys_texture_and_reduces_colours(face):
    f = make_frame()
    apply_treatment(f, face, Treatment.MOSAIC)
    roi = f[40:80, 60:100].reshape(-1, 3)
    assert len(np.unique(roi, axis=0)) <= 6 * 6 + 4


def test_blur_cuts_variance_massively(face):
    f = make_frame(); before = region_std(f, face)
    apply_treatment(f, face, Treatment.BLUR)
    assert region_std(f, face) < before * 0.25


def test_swap_unimplemented_fails_closed(face):
    f = make_frame()
    apply_treatment(f, face, Treatment.SWAP)
    assert f[40:80, 60:100].max() == 0


def test_out_of_frame_and_degenerate_boxes_are_safe():
    f = make_frame()
    apply_treatment(f, Box(-50, -50, 5, 5), Treatment.BLOCK)
    apply_treatment(f, Box(500, 500, 600, 600), Treatment.BLOCK)
    apply_treatment(f, Box(10, 10, 10, 10), Treatment.BLOCK)
    apply_full_frame(f, Treatment.BLOCK)
    assert f.max() == 0
