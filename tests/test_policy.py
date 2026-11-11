import itertools
import numpy as np
from privacyfirst.policy import PolicyConfig, PolicyEngine
from privacyfirst.tracking import Track
from privacyfirst.types import Box, Treatment, STRENGTH


def trk(conf=0.9, misses=0, minor=None):
    return Track(1, Box(0, 0, 10, 10), conf=conf, misses=misses, minor_prob=minor)


def test_unknown_age_is_minor_by_default_so_mosaic():
    assert PolicyEngine().decide(trk()).treatment == Treatment.MOSAIC


def test_standard_profile_unknown_age_blurs_only():
    e = PolicyEngine(PolicyConfig.standard())
    assert e.decide(trk()).treatment == Treatment.BLUR


def test_low_confidence_and_ghost_escalate_to_mosaic_even_in_standard():
    e = PolicyEngine(PolicyConfig.standard())
    assert e.decide(trk(conf=0.2)).treatment == Treatment.MOSAIC
    assert e.decide(trk(misses=2)).treatment == Treatment.MOSAIC


def test_likely_minor_gets_minor_treatment_in_standard():
    e = PolicyEngine(PolicyConfig.standard())
    assert e.decide(trk(minor=0.3)).treatment == Treatment.MOSAIC
    assert e.decide(trk(minor=0.05)).treatment == Treatment.BLUR


def test_policy_never_emits_swap_or_pass_in_phase1():
    for cfg in (PolicyConfig.strict(), PolicyConfig.standard()):
        e = PolicyEngine(cfg)
        for conf, miss, minor in itertools.product((0.0, 0.4, 0.9), (0, 3), (None, 0.0, 0.5, 1.0)):
            t = e.decide(trk(conf, miss, minor)).treatment
            assert STRENGTH[t] >= STRENGTH[Treatment.BLUR]


def test_scene_checks_fail_closed():
    e = PolicyEngine()
    assert e.scene_decision(np.full((8, 8, 3), 128, np.uint8), True) is None
    assert e.scene_decision(np.full((8, 8, 3), 128, np.uint8), False).treatment == Treatment.BLOCK
    assert e.scene_decision(np.zeros((8, 8, 3), np.uint8), True).treatment == Treatment.MOSAIC
