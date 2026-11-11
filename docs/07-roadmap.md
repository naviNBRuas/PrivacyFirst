# 07. Roadmap

Time estimates assume one focused builder; treat them as planning ranges.

| Phase | Goal | Exit criteria | Est. |
|---|---|---|---|
| **0. Feasibility** | Pick platform; bake-off detectors/swap models; license clearance; build benchmark set | Written license memo; benchmark with ground truth; go/no-go on photoreal swap | 3-4 wk |
| **1. Safe core** (this repo, run 001) | Fail-closed privacyfirst for recorded video with report | Tests green; real detector + independent verifier integrated; metadata verified | 6-8 wk |
| **1b. Two-pass recorded mode** | Close the lookahead gap with bidirectional tracking | Zero leak frames on benchmark clips with late first detections | 2-3 wk |
| **2. Identity replacement** | Vetted identity library, full-head swap, stabilizer, recognizer-ensemble verification, review UI v1 | Verifier pass rate target met; flicker metric under threshold; minors default non-photoreal | 6-8 wk |
| **3. Live mode** | Lookahead + budget governor, live preview, RAM-only guarantees, desktop virtual camera | <=150 ms; degrades to blur under load; no raw-frame persistence test | 6-8 wk |
| **4. Hardening + beta** | Age model calibration, guardian gate, context scan, voice anonymization, red team, legal review | Red-team findings closed; legal sign-off on copy; closed beta | 6+ wk |

## Runs
- **Run 001 (done):** Phase 1 safe core + docs.
- **Run 002 (done):** Phase 0 benchmark harness, real-detector adapters, identity-replacement design (docs/12), Phase 0 plan and license templates.
- **Run 003 (done):** Swap gates in policy, `FaceReplacer` protocol + stub, identity library/assignment, head mask + blending, stabilizers + flicker metric, recognizer-ensemble wiring, swap benchmark, docs 13, ADR 0006-0007.
- **Run 004 (next):** Tracker upgrade for ID stability (ByteTrack/OC-SORT + ephemeral re-ID) and two-pass recorded mode (Phase 1b); tune swap share vs hysteresis (measured 44% baseline); segmentation-ready head mask interface.
- **Run 005a (done, no weights needed):** two-pass early release, detector-measurement kit, `--detector` CLI, exit-expiry negative result.
- **Run 005b:** Real models (needs weights: allow the host or run locally): detector + recognizer ensemble + swap backend, threshold calibration, first real-footage benchmark.
- **Run 006 (done):** Context-identifier scan v0 (OCR + rules, plate-shape finder, live and two-pass sources, benchmark) and the review-flow data model (docs 16, 17).
- **Run 007 (candidates):** (a) run 005b with real weights (needs you); (b) calibrate the context scan on real footage (needs you); (c) audio path: voice-anonymization design and a keep-audio pipeline scaffold; (d) guardian gate + review UI prototype.

## Risks to the schedule
Swap-model licensing; real-time cost on mid-range phones; age-estimation fairness; verifier
independence; legal review lead time.
