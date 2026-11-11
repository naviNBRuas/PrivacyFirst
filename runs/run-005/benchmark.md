# Benchmark: leak rate by scenario and pipeline variant

Seeds: 5, frames/clip: 120. **SIMULATED detector failure modes. Measures pipeline behaviour, not real detector accuracy.**

Leak rate = share of visible face-frames with <90% of the face box covered by redaction. Lower is better.

| Scenario | Detector miss | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 | legacy_tracker+look4 | two_pass |
|---|---|---|---|---|---|---|---|---|
| baseline | 4.8% | 2.7% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| tiny_faces | 60.7% | 58.0% | 26.1% | 25.8% | 25.1% | 22.4% | 25.1% | 25.6% |
| low_light | 67.4% | 61.1% | 5.4% | 4.4% | 3.2% | 2.5% | 4.8% | 0.0% |
| motion_blur | 32.0% | 24.8% | 3.8% | 3.4% | 3.4% | 3.4% | 6.8% | 1.2% |
| occlusion | 14.4% | 11.1% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| crowd | 14.8% | 9.9% | 0.4% | 0.2% | 0.0% | 0.0% | 0.5% | 0.0% |
| late_appearance | 14.2% | 11.8% | 9.4% | 6.9% | 3.6% | 0.0% | 6.9% | 0.0% |
| late_long | 28.3% | 26.7% | 23.4% | 22.3% | 20.1% | 15.3% | 21.4% | 10.7% |
| edge_entry | 15.0% | 11.4% | 3.6% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| erratic_motion | 19.7% | 13.8% | 0.2% | 0.0% | 0.0% | 0.0% | 0.4% | 0.0% |
| exit_reenter | 5.2% | 3.0% | 0.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

## Cost: mean share of the frame that is redacted

| Scenario | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 | legacy_tracker+look4 | two_pass |
|---|---|---|---|---|---|---|---|
| baseline | 35.3% | 48.2% | 48.7% | 49.5% | 52.0% | 50.5% | 50.3% |
| tiny_faces | 3.6% | 28.6% | 29.0% | 30.0% | 33.8% | 34.7% | 27.1% |
| low_light | 14.7% | 69.5% | 70.2% | 71.8% | 75.4% | 67.1% | 73.9% |
| motion_blur | 24.9% | 67.7% | 69.4% | 73.2% | 81.9% | 65.0% | 83.0% |
| occlusion | 23.7% | 52.5% | 53.1% | 53.9% | 55.8% | 53.0% | 49.2% |
| crowd | 42.1% | 55.8% | 55.9% | 56.2% | 57.6% | 58.7% | 52.7% |
| late_appearance | 33.5% | 46.7% | 48.6% | 52.2% | 57.9% | 48.6% | 52.8% |
| late_long | 27.9% | 47.7% | 49.1% | 51.7% | 58.5% | 50.8% | 56.3% |
| edge_entry | 14.5% | 35.6% | 36.9% | 38.5% | 41.1% | 35.0% | 39.6% |
| erratic_motion | 29.7% | 51.5% | 52.4% | 54.6% | 60.5% | 52.2% | 52.0% |
| exit_reenter | 23.8% | 46.2% | 47.6% | 50.3% | 56.9% | 43.6% | 57.5% |

## Track-ID changes per scenario (matters for stable synthetic identity in Phase 2)

| Scenario | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 | legacy_tracker+look4 | two_pass |
|---|---|---|---|---|---|---|---|
| baseline | 29 | 4 | 4 | 6 | 6 | 4 | 4 |
| tiny_faces | 69 | 17 | 17 | 17 | 17 | 38 | 4 |
| low_light | 85 | 20 | 21 | 21 | 23 | 27 | 11 |
| motion_blur | 133 | 77 | 78 | 78 | 78 | 119 | 44 |
| occlusion | 58 | 20 | 20 | 21 | 20 | 18 | 14 |
| crowd | 326 | 67 | 67 | 67 | 67 | 99 | 62 |
| late_appearance | 24 | 4 | 5 | 7 | 7 | 5 | 7 |
| late_long | 20 | 7 | 9 | 12 | 12 | 11 | 12 |
| edge_entry | 13 | 3 | 3 | 3 | 3 | 3 | 3 |
| erratic_motion | 83 | 24 | 25 | 25 | 27 | 45 | 14 |
| exit_reenter | 42 | 21 | 21 | 21 | 21 | 20 | 21 |
