from privacyfirst.bench.measure import estimate
from privacyfirst.bench.simdet import SimulatedDetector
from privacyfirst.bench.synth import make_clip


def test_estimate_recovers_simulator_profile_within_a_factor():
    """Round trip on a clip with KNOWN parameters (baseline: p_enter_miss 0.02, mean_burst 3, min_size 14)."""
    logs = []
    for seed in range(6):
        clip = make_clip("baseline", seed, 300)
        sd = SimulatedDetector(clip, seed)
        w, h = clip.render(0).shape[1], clip.render(0).shape[0]
        logs.append(([sd.detect(clip.render(i)) for i in range(clip.n_frames)], w, h))
    ests = [estimate(l, w, h)["suggested_profile"] for l, w, h in logs]
    p = sum(e["p_enter_miss"] for e in ests) / len(ests)
    b = sum(e["mean_burst"] for e in ests) / len(ests)
    assert 0.01 < p < 0.06, p            # truth 0.02
    assert 1.5 < b < 6.0, b              # truth 3.0


def test_estimate_handles_empty_and_detectionless_input():
    e = estimate([[] for _ in range(10)], 100, 100)
    assert e["detections"] == 0 and e["suggested_profile"]["p_enter_miss"] == 0.0
