# 11. Benchmark Harness (Phase 0)

Code: `src/privacyfirst/bench/`. Run: `python -m privacyfirst.bench --out runs/bench --seeds 5 --frames 120`.

## What it measures
| Piece | Purpose |
|---|---|
| `synth.py` | Deterministic synthetic clips with per-frame ground truth for 10 hard-case scenarios: baseline, tiny_faces, low_light, motion_blur, occlusion, crowd, late_appearance, edge_entry, erratic_motion, exit_reenter |
| `simdet.py` | **Simulated** detector: bursty miss process (two-state Markov), min size, visible-fraction limits, blind period, box jitter, false positives |
| `metrics.py` | Coverage of each ground-truth face by the pipeline's applied regions; leak = <90% covered; severe = <50%; track-ID changes per face |
| `runner.py` | Runs five pipeline variants (detect_only, ghost, ghost+look4/8/16) over scenarios and seeds; markdown/JSON/PNG output; `evaluate_detector()` for any real detector |
| `adapters/` | `MediaPipeFaceDetector`, `YuNetDetector` behind the `Detector` protocol (model files not bundled) |

## What it does NOT measure
Real detector accuracy. The simulator applies *assumed* failure patterns to drawn faces. It answers "how much
of a detector's misses does the pipeline recover, at what over-redaction cost?" Real recall, FPPI and latency
come from `evaluate_detector(real_detector, real_clips)` on consented footage.

## First findings (run 002, 5 seeds x 120 frames, see `runs/run-002/benchmark.md`)
- Ghost tracks cut leaks dramatically for correlated dropouts (low light, motion blur, occlusion, crowds).
- A face the detector **never** sees cannot be recovered: tiny faces still leak (the floor is set by the detector).
- Late appearance leaks until lookahead exceeds the blind period (confirms Phase 1b two-pass need).
- Over-redaction cost rises with ghost tracks and lookahead: more of the frame is covered.
- Track IDs fragment in motion blur and crowds: a blocker for stable synthetic identities (Phase 2).
- Scene scale note: synthetic faces are large relative to the 192x144 frame, so the area-cost figures are
  inflated versus real footage; compare variants against each other, not against reality.

## Phase 0 use
Swap in a real detector and verifier via the adapters, build the consented benchmark set (see
`docs/phase0/PHASE0_PLAN.md`), and use the same metrics to choose models.
