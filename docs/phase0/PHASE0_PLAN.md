# Phase 0 Plan: Feasibility and Model Selection

**Exit gate:** written license clearance for every shipped model, a benchmark with ground truth, measured
real-model numbers on target hardware, and a go/no-go on photoreal replacement.

## Workstreams
| # | Task | Output | Status |
|---|---|---|---|
| 1 | Benchmark harness (synthetic hard cases, leak metrics) | `bench/` | Done (run 002) |
| 2 | Real detector adapters (MediaPipe, YuNet) | `adapters/` | Written, **untested against real weights** |
| 3 | Obtain model files locally; run `evaluate_detector` | Recall/FPPI/latency table | Needs you (see MODEL_SETUP) |
| 4 | Consented/synthetic real-footage benchmark set with ground truth | Dataset + spec | Not started |
| 5 | Swap-model candidates evaluation (quality, leak, latency, license) | Scorecard | Not started |
| 6 | Recognizer-ensemble selection + thresholds | Verifier choice | Not started |
| 7 | License clearance memo per model | `license-clearance-memo-TEMPLATE.md` filled | Template ready |
| 8 | Platform decision (D1) | ADR | Default: Apple Silicon Mac first |

## Dataset spec (minimum)
Consented or fully synthetic; lighting extremes, motion blur, profile/occluded/masked, tiny/far, crowds,
varied skin tones and ages; children only with documented guardian consent and ethics review; ground-truth boxes
per frame; versioned; raw media never committed to git.

## Go/no-go criteria for photoreal replacement
At least one swap candidate with a cleared license achieves: recognizer match-rate below calibrated thresholds on
every ensemble member, acceptable flicker, and latency within budget on target hardware. Otherwise ship
Phase 1 (destructive redaction) first and keep researching.
