# 08. Test and Verification Plan

## Layers
| Layer | What | Where |
|---|---|---|
| Unit | Policy rules, tracker, fallbacks, metadata, report | `tests/` |
| Invariant | Every output frame covers every tracked face; detector failure -> blocked frame; verifier escalation | `tests/test_pipeline.py` |
| Structural | No network-capable imports | `tests/test_no_network.py` |
| Characterization | Documents known limits (late first detection beyond lookahead) | `test_KNOWN_LIMIT_*` |
| Benchmark (Phase 0+) | Recall@FPPI, leak frames per hour, verifier match-rate, latency, flicker | planned harness |
| Red team (Phase 4) | Commercial recognition APIs, human reviewers, adversarial footage | planned |

## Current suite (68 tests)
Policy (6), tracking (4), fallback (5), pipeline (9 incl. 1 known-limit), metadata (2), structural (1), benchmark/adapters/swap-bench (8),
identity (8), stabilizer + blend (5), swap policy (8), swap pipeline (13: gates, sticky demotion, late-failure demotion, budget,
identity persistence/collisions/release, minors, residual-scan interplay, geometric coverage).
Run: `python -m pytest -q`.

## Invariants (must hold at every release)
1. Treatment strength never decreases through any rule.
2. A detector exception never yields an unredacted frame.
3. A face that remains in the scene during a detector dropout (<= max ghost frames) stays covered.
4. Verifier failure never yields an unverified frame passing as clean.
5. Reports contain no pixel data, embeddings, or metadata values.
6. Output files contain no personal metadata keys or GPS tags (ffprobe-verified).

## Benchmark set requirements (Phase 0)
Consented or synthetic only. Cover: lighting extremes, motion blur, profile/occluded/masked,
tiny/far faces, crowds, children (consented, ethics-reviewed), varied skin tones and ages, camera
shake, rolling shutter. Ground-truth boxes per frame. Version the set; never commit raw media to git.

## Metrics and targets
| Metric | Target |
|---|---|
| Leak frames (detectable unredacted face) | 0 |
| Recall of primary detector at agreed FPPI | tracked, no regression |
| Verifier match-rate on swapped faces (Phase 2) | below calibrated threshold on every recognizer in the ensemble |
| Identity flicker | below calibrated threshold |
| p95 live latency | <=150 ms |

## Known gaps in testing today
Haar placeholder is not representative; the demo verifier is scripted; no real-footage benchmark yet.
