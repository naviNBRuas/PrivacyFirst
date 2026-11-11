# Face-change benchmark: tracker and mode comparison (run 004)

All configurations use the same clips, seeds and default policy. **STUB replacer + SIMULATED detector.** Leak rate counts a swapped head box as covered (limitation 22), so it does not judge swap quality. Averages are weighted by face-frames across all scenarios.

| Configuration | Swap share | Leak rate | Identity changes / person | Swap<->fallback flips / 100 face-frames | Collisions |
|---|---|---|---|---|---|
| live, legacy tracker (current gates) | 40.8% | 5.77% | 1.11 | 5.5 | 0 |
| live, run-004 tracker | 39.9% | 5.71% | 0.84 | 5.5 | 0 |
| two-pass | 73.7% | 3.83% | 0.89 | 4.0 | 0 |

## live, legacy tracker (current gates)

Seeds: 3, frames/clip: 120. **STUB replacer + SIMULATED detector. Measures the gates and bookkeeping, not real swap quality.**

Shares are of visible face-frames, by the treatment actually applied. Strict profile: unknown age is minor-risk, so every swap needed an explicit recognizer-ensemble PASS.

| Scenario | Swap | Mosaic | Blur | Block | Uncovered | Leak rate | Identity changes / person | Collisions |
|---|---|---|---|---|---|---|---|---|
| baseline | 62% | 38% | 0% | 0% | 0.0% | 0.0% | 0.33 | 0 |
| tiny_faces | 15% | 50% | 0% | 0% | 34.9% | 24.8% | 1.00 | 0 |
| low_light | 0% | 90% | 0% | 0% | 9.7% | 6.1% | 0.00 | 0 |
| motion_blur | 29% | 69% | 0% | 0% | 2.2% | 5.8% | 4.33 | 0 |
| occlusion | 54% | 45% | 0% | 0% | 0.9% | 0.0% | 1.17 | 0 |
| crowd | 42% | 58% | 0% | 0% | 0.3% | 0.2% | 1.33 | 0 |
| late_appearance | 59% | 33% | 0% | 0% | 7.1% | 7.1% | 0.17 | 0 |
| late_long | 53% | 29% | 0% | 0% | 17.5% | 21.2% | 0.17 | 0 |
| edge_entry | 57% | 43% | 0% | 0% | 0.0% | 0.0% | 0.17 | 0 |
| erratic_motion | 33% | 67% | 0% | 0% | 0.0% | 0.7% | 2.17 | 0 |
| exit_reenter | 70% | 30% | 0% | 0% | 0.0% | 0.0% | 1.33 | 0 |

## Why faces were demoted from swap (counts)

| Scenario | Reasons |
|---|---|
| baseline | sticky_demotion: 471, minor_gate_not_passed: 296, ghost_track: 274, track_not_stable: 262, low_confidence: 11 |
| tiny_faces | sticky_demotion: 1065, ghost_track: 902, minor_gate_not_passed: 772, track_not_stable: 466, low_confidence: 11 |
| low_light | minor_gate_not_passed: 896, sticky_demotion: 870, ghost_track: 688, track_not_stable: 413, low_confidence: 207 |
| motion_blur | sticky_demotion: 1340, ghost_track: 1261, minor_gate_not_passed: 807, track_not_stable: 596, low_confidence: 5 |
| occlusion | sticky_demotion: 552, ghost_track: 385, minor_gate_not_passed: 339, track_not_stable: 280, low_confidence: 9 |
| crowd | sticky_demotion: 1902, ghost_track: 906, minor_gate_not_passed: 661, no_identity: 389, track_not_stable: 288 |
| late_appearance | sticky_demotion: 379, ghost_track: 251, track_not_stable: 243, minor_gate_not_passed: 243, low_confidence: 8 |
| late_long | sticky_demotion: 464, minor_gate_not_passed: 411, track_not_stable: 386, ghost_track: 377, low_confidence: 13 |
| edge_entry | sticky_demotion: 381, ghost_track: 318, minor_gate_not_passed: 183, track_not_stable: 149, low_confidence: 5 |
| erratic_motion | sticky_demotion: 961, ghost_track: 727, minor_gate_not_passed: 444, track_not_stable: 301, low_confidence: 11 |
| exit_reenter | sticky_demotion: 533, ghost_track: 443, minor_gate_not_passed: 307, track_not_stable: 248, low_confidence: 7 |

## Temporal stability: persistent identity vs re-picking every frame (flicker, lower = steadier)

| Scenario | Persistent | Churn counterfactual |
|---|---|---|


## live, run-004 tracker

Seeds: 3, frames/clip: 120. **STUB replacer + SIMULATED detector. Measures the gates and bookkeeping, not real swap quality.**

Shares are of visible face-frames, by the treatment actually applied. Strict profile: unknown age is minor-risk, so every swap needed an explicit recognizer-ensemble PASS.

| Scenario | Swap | Mosaic | Blur | Block | Uncovered | Leak rate | Identity changes / person | Collisions |
|---|---|---|---|---|---|---|---|---|
| baseline | 62% | 38% | 0% | 0% | 0.0% | 0.0% | 0.33 | 0 |
| tiny_faces | 10% | 50% | 0% | 0% | 39.3% | 26.4% | 0.50 | 0 |
| low_light | 0% | 88% | 0% | 0% | 11.7% | 6.7% | 0.00 | 0 |
| motion_blur | 25% | 70% | 0% | 0% | 4.9% | 1.5% | 3.50 | 0 |
| occlusion | 52% | 47% | 0% | 0% | 1.0% | 0.0% | 1.00 | 0 |
| crowd | 44% | 56% | 0% | 0% | 0.7% | 0.2% | 1.04 | 0 |
| late_appearance | 59% | 33% | 0% | 0% | 7.1% | 7.1% | 0.17 | 0 |
| late_long | 51% | 31% | 0% | 0% | 18.1% | 22.4% | 0.17 | 0 |
| edge_entry | 57% | 43% | 0% | 0% | 0.0% | 0.0% | 0.17 | 0 |
| erratic_motion | 27% | 72% | 0% | 0% | 1.0% | 0.1% | 1.00 | 0 |
| exit_reenter | 70% | 30% | 0% | 0% | 0.0% | 0.0% | 1.33 | 0 |

## Why faces were demoted from swap (counts)

| Scenario | Reasons |
|---|---|
| baseline | sticky_demotion: 463, minor_gate_not_passed: 286, ghost_track: 264, track_not_stable: 252, low_confidence: 11 |
| tiny_faces | sticky_demotion: 812, ghost_track: 548, minor_gate_not_passed: 535, track_not_stable: 189, low_confidence: 11 |
| low_light | minor_gate_not_passed: 799, sticky_demotion: 780, ghost_track: 591, track_not_stable: 290, low_confidence: 207 |
| motion_blur | sticky_demotion: 1027, ghost_track: 836, minor_gate_not_passed: 588, track_not_stable: 342, low_confidence: 5 |
| occlusion | sticky_demotion: 554, ghost_track: 375, minor_gate_not_passed: 329, track_not_stable: 270, low_confidence: 9 |
| crowd | sticky_demotion: 1650, ghost_track: 578, minor_gate_not_passed: 250, track_not_stable: 224, no_identity: 62 |
| late_appearance | sticky_demotion: 379, ghost_track: 251, track_not_stable: 243, minor_gate_not_passed: 243, low_confidence: 8 |
| late_long | sticky_demotion: 457, minor_gate_not_passed: 390, track_not_stable: 337, ghost_track: 336, low_confidence: 13 |
| edge_entry | sticky_demotion: 381, ghost_track: 318, minor_gate_not_passed: 183, track_not_stable: 149, low_confidence: 5 |
| erratic_motion | sticky_demotion: 778, ghost_track: 446, minor_gate_not_passed: 383, track_not_stable: 221, low_confidence: 11 |
| exit_reenter | sticky_demotion: 523, ghost_track: 428, minor_gate_not_passed: 292, track_not_stable: 229, low_confidence: 7 |

## Temporal stability: persistent identity vs re-picking every frame (flicker, lower = steadier)

| Scenario | Persistent | Churn counterfactual |
|---|---|---|
| baseline | 4.8 | 18.7 |
| tiny_faces | 7.4 | 18.5 |
| motion_blur | 9.0 | 18.8 |
| occlusion | 5.7 | 18.9 |
| crowd | 8.9 | 21.8 |
| late_appearance | 4.2 | 18.4 |
| late_long | 4.6 | 18.2 |
| edge_entry | 4.6 | 19.0 |
| erratic_motion | 6.6 | 18.9 |
| exit_reenter | 5.0 | 19.6 |


## two-pass

Seeds: 3, frames/clip: 120. **STUB replacer + SIMULATED detector. Measures the gates and bookkeeping, not real swap quality.**

Shares are of visible face-frames, by the treatment actually applied. Strict profile: unknown age is minor-risk, so every swap needed an explicit recognizer-ensemble PASS.

| Scenario | Swap | Mosaic | Blur | Block | Uncovered | Leak rate | Identity changes / person | Collisions |
|---|---|---|---|---|---|---|---|---|
| baseline | 97% | 3% | 0% | 0% | 0.0% | 0.0% | 0.33 | 0 |
| tiny_faces | 36% | 19% | 0% | 0% | 45.1% | 26.9% | 0.50 | 0 |
| low_light | 0% | 81% | 0% | 0% | 18.9% | 0.0% | 0.00 | 0 |
| motion_blur | 65% | 25% | 0% | 0% | 9.7% | 0.1% | 3.50 | 0 |
| occlusion | 88% | 12% | 0% | 0% | 0.3% | 0.0% | 1.00 | 0 |
| crowd | 90% | 9% | 0% | 0% | 0.6% | 0.0% | 1.29 | 0 |
| late_appearance | 84% | 13% | 0% | 0% | 2.4% | 0.0% | 0.17 | 0 |
| late_long | 67% | 22% | 0% | 0% | 10.7% | 11.8% | 0.17 | 0 |
| edge_entry | 81% | 19% | 0% | 0% | 0.0% | 0.0% | 0.17 | 0 |
| erratic_motion | 84% | 11% | 0% | 0% | 5.0% | 0.1% | 1.00 | 0 |
| exit_reenter | 96% | 4% | 0% | 0% | 0.0% | 0.0% | 1.67 | 0 |

## Why faces were demoted from swap (counts)

| Scenario | Reasons |
|---|---|
| baseline | sticky_demotion: 279, ghost_track: 273, track_not_stable: 269, minor_gate_not_passed: 269, low_confidence: 11 |
| tiny_faces | sticky_demotion: 576, ghost_track: 517, minor_gate_not_passed: 160, track_not_stable: 150, low_confidence: 11 |
| low_light | minor_gate_not_passed: 848, sticky_demotion: 723, ghost_track: 597, low_confidence: 250, track_not_stable: 171 |
| motion_blur | sticky_demotion: 887, ghost_track: 843, minor_gate_not_passed: 277, track_not_stable: 244, low_confidence: 5 |
| occlusion | sticky_demotion: 419, ghost_track: 413, track_not_stable: 311, minor_gate_not_passed: 311, low_confidence: 9 |
| crowd | sticky_demotion: 450, ghost_track: 392, minor_gate_not_passed: 153, track_not_stable: 141, no_identity: 35 |
| late_appearance | minor_gate_not_passed: 364, sticky_demotion: 362, ghost_track: 354, track_not_stable: 352, low_confidence: 8 |
| late_long | sticky_demotion: 467, minor_gate_not_passed: 458, ghost_track: 451, track_not_stable: 438, low_confidence: 13 |
| edge_entry | sticky_demotion: 390, ghost_track: 384, minor_gate_not_passed: 211, track_not_stable: 197, low_confidence: 5 |
| erratic_motion | sticky_demotion: 312, ghost_track: 292, minor_gate_not_passed: 200, track_not_stable: 195, low_confidence: 15 |
| exit_reenter | sticky_demotion: 532, ghost_track: 526, minor_gate_not_passed: 305, track_not_stable: 285, low_confidence: 8 |

## Temporal stability: persistent identity vs re-picking every frame (flicker, lower = steadier)

| Scenario | Persistent | Churn counterfactual |
|---|---|---|

