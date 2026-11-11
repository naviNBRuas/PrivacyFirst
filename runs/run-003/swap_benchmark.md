# Face-change (swap) benchmark

Seeds: 3, frames/clip: 120. **STUB replacer + SIMULATED detector. Measures the gates and bookkeeping, not real swap quality.**

Shares are of visible face-frames, by the treatment actually applied. Strict profile: unknown age is minor-risk, so every swap needed an explicit recognizer-ensemble PASS.

| Scenario | Swap | Mosaic | Blur | Block | Uncovered | Leak rate | Identity changes / person | Collisions |
|---|---|---|---|---|---|---|---|---|
| baseline | 44% | 56% | 0% | 0% | 0.0% | 0.0% | 0.33 | 0 |
| tiny_faces | 13% | 52% | 0% | 0% | 34.9% | 25.0% | 1.00 | 0 |
| low_light | 0% | 90% | 0% | 0% | 9.7% | 6.1% | 0.00 | 0 |
| motion_blur | 27% | 71% | 0% | 0% | 2.2% | 5.8% | 4.17 | 0 |
| occlusion | 44% | 55% | 0% | 0% | 0.9% | 0.0% | 0.83 | 0 |
| crowd | 26% | 74% | 0% | 0% | 0.3% | 0.2% | 0.78 | 0 |
| late_appearance | 51% | 42% | 0% | 0% | 7.1% | 7.1% | 0.17 | 0 |
| edge_entry | 46% | 54% | 0% | 0% | 0.0% | 0.0% | 0.00 | 0 |
| erratic_motion | 25% | 75% | 0% | 0% | 0.0% | 0.6% | 1.83 | 0 |
| exit_reenter | 60% | 40% | 0% | 0% | 0.0% | 0.0% | 1.17 | 0 |

## Why faces were demoted from swap (counts)

| Scenario | Reasons |
|---|---|
| baseline | sticky_demotion: 596, minor_gate_not_passed: 311, ghost_track: 274, track_not_stable: 262, low_confidence: 11 |
| tiny_faces | sticky_demotion: 1087, ghost_track: 902, minor_gate_not_passed: 772, track_not_stable: 466, low_confidence: 11 |
| low_light | minor_gate_not_passed: 896, sticky_demotion: 870, ghost_track: 688, track_not_stable: 413, low_confidence: 207 |
| motion_blur | sticky_demotion: 1355, ghost_track: 1261, minor_gate_not_passed: 833, track_not_stable: 596, low_confidence: 5 |
| occlusion | sticky_demotion: 626, ghost_track: 385, minor_gate_not_passed: 339, track_not_stable: 280, low_confidence: 9 |
| crowd | sticky_demotion: 2383, ghost_track: 906, minor_gate_not_passed: 724, no_identity: 389, track_not_stable: 288 |
| late_appearance | sticky_demotion: 456, ghost_track: 251, track_not_stable: 243, minor_gate_not_passed: 243, low_confidence: 8 |
| edge_entry | sticky_demotion: 418, ghost_track: 318, minor_gate_not_passed: 221, track_not_stable: 149, low_confidence: 5 |
| erratic_motion | sticky_demotion: 1025, ghost_track: 727, minor_gate_not_passed: 520, track_not_stable: 301, low_confidence: 11 |
| exit_reenter | sticky_demotion: 583, ghost_track: 443, minor_gate_not_passed: 326, track_not_stable: 248, low_confidence: 7 |

## Temporal stability: persistent identity vs re-picking every frame (flicker, lower = steadier)

| Scenario | Persistent | Churn counterfactual |
|---|---|---|
| baseline | 5.2 | 18.2 |
| tiny_faces | 7.3 | 18.3 |
| motion_blur | 8.3 | 22.1 |
| occlusion | 4.6 | 19.8 |
| crowd | 8.2 | 21.0 |
| late_appearance | 4.9 | 18.5 |
| edge_entry | 4.8 | 18.1 |
| erratic_motion | 5.4 | 17.9 |
| exit_reenter | 5.0 | 19.3 |
