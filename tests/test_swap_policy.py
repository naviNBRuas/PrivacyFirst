from privacyfirst.policy import PolicyConfig, PolicyEngine, SwapContext
from privacyfirst.tracking import Track
from privacyfirst.types import Box, Treatment


def trk(conf=0.9, hits=10, misses=0, minor=0.0):
    return Track(1, Box(0, 0, 40, 40), conf=conf, hits=hits, misses=misses, minor_prob=minor)


def eng(**kw):
    return PolicyEngine(PolicyConfig(swap_enabled=True, unknown_age_is_minor=False, **kw))


def ctx(**kw):
    d = dict(health=0.9, budget_ok=True, identity_ok=True, demoted=False, verified=True, minor_gate_ok=True)
    d.update(kw)
    return SwapContext(**d)


def why(e, t, c):
    return [r.split(":", 1)[1] for r in e.decide(t, c).reasons if r.startswith("swap_gate:")]


def test_swap_off_by_default_and_without_context():
    assert PolicyEngine(PolicyConfig()).decide(trk(), ctx()).treatment != Treatment.SWAP
    assert eng().decide(trk()).treatment != Treatment.SWAP


def test_all_gates_pass_gives_swap():
    assert eng().decide(trk(), ctx()).treatment == Treatment.SWAP


def test_each_gate_blocks_swap_and_demotes_to_mosaic():
    e = eng()
    cases = {
        "ghost_track": (trk(misses=1), ctx()), "low_confidence": (trk(conf=0.5), ctx()),
        "track_not_stable": (trk(hits=2), ctx()), "no_identity": (trk(), ctx(identity_ok=False)),
        "sticky_demotion": (trk(), ctx(demoted=True)), "replacer_error": (trk(), ctx(replacer_error=True)),
        "replacer_unhealthy": (trk(), ctx(health=0.3)), "verification_failed": (trk(), ctx(verified=False)),
    }
    for name, (t, c) in cases.items():
        d = e.decide(t, c)
        assert name in why(e, t, c) and d.treatment == Treatment.MOSAIC, name


def test_not_evaluated_health_never_swaps_on_faith():
    e = eng()
    assert why(e, trk(), ctx(health=None)) == ["replacer_unhealthy"]


def test_over_budget_demotes_to_blur_not_mosaic():
    d = eng().decide(trk(), ctx(budget_ok=False))
    assert d.treatment == Treatment.BLUR


def test_minor_risk_needs_explicit_pass_child_ok_identity_and_enabled_path():
    e = eng()
    m = trk(minor=0.6)
    assert e.decide(m, ctx()).treatment == Treatment.SWAP                     # strict gate satisfied
    assert "minor_gate_not_passed" in why(e, m, ctx(verified=None))           # "not checked" is not a pass
    assert "minor_gate_not_passed" in why(e, m, ctx(minor_gate_ok=False))
    off = PolicyEngine(PolicyConfig(swap_enabled=True, unknown_age_is_minor=False, minor_swap_allowed=False))
    assert off.decide(m, ctx()).treatment == Treatment.MOSAIC
    unk = PolicyEngine(PolicyConfig(swap_enabled=True))                       # strict profile: unknown age = minor
    assert unk.decide(Track(1, Box(0, 0, 40, 40), conf=0.9, hits=10), ctx(verified=None)).treatment == Treatment.MOSAIC


def test_demotion_never_weaker_than_base_rules():
    e = PolicyEngine(PolicyConfig(swap_enabled=True, swap_demote_treatment=Treatment.BLUR))
    assert e.decide(Track(1, Box(0, 0, 9, 9), conf=0.9, hits=1), ctx(verified=None)).treatment == Treatment.MOSAIC
