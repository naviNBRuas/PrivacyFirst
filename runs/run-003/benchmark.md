# Benchmark: leak rate by scenario and pipeline variant

Seeds: 5, frames/clip: 120. **SIMULATED detector failure modes. Measures pipeline behaviour, not real detector accuracy.**

Leak rate = share of visible face-frames with <90% of the face box covered by redaction. Lower is better.

| Scenario | Detector miss | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 |
|---|---|---|---|---|---|---|
| baseline | 4.8% | 2.7% | 0.0% | 0.0% | 0.0% | 0.0% |
| tiny_faces | 60.7% | 57.9% | 26.6% | 25.1% | 23.7% | 19.6% |
| low_light | 67.4% | 61.1% | 6.7% | 4.8% | 3.1% | 1.8% |
| motion_blur | 32.0% | 24.8% | 8.3% | 6.8% | 5.5% | 3.2% |
| occlusion | 14.4% | 11.1% | 0.0% | 0.0% | 0.0% | 0.0% |
| crowd | 14.8% | 9.9% | 0.9% | 0.5% | 0.2% | 0.0% |
| late_appearance | 14.2% | 11.8% | 9.4% | 6.9% | 3.6% | 0.0% |
| edge_entry | 15.0% | 11.4% | 3.6% | 0.0% | 0.0% | 0.0% |
| erratic_motion | 19.7% | 13.8% | 1.3% | 0.4% | 0.1% | 0.0% |
| exit_reenter | 5.2% | 3.0% | 0.3% | 0.0% | 0.0% | 0.0% |

## Cost: mean share of the frame that is redacted

| Scenario | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 |
|---|---|---|---|---|---|
| baseline | 35.3% | 50.0% | 50.5% | 51.5% | 54.4% |
| tiny_faces | 3.6% | 34.1% | 34.7% | 36.0% | 41.6% |
| low_light | 14.7% | 66.2% | 67.1% | 69.3% | 75.4% |
| motion_blur | 25.0% | 61.0% | 65.0% | 72.4% | 86.7% |
| occlusion | 23.7% | 52.4% | 53.0% | 53.9% | 56.2% |
| crowd | 42.1% | 58.3% | 58.7% | 59.8% | 64.1% |
| late_appearance | 33.5% | 46.6% | 48.6% | 52.1% | 57.8% |
| edge_entry | 14.5% | 33.8% | 35.0% | 36.7% | 39.2% |
| erratic_motion | 29.7% | 50.3% | 52.2% | 56.4% | 67.5% |
| exit_reenter | 23.8% | 41.9% | 43.6% | 46.5% | 53.6% |

## Track-ID changes per scenario (matters for stable synthetic identity in Phase 2)

| Scenario | detect_only | ghost | ghost+look4 | ghost+look8 | ghost+look16 |
|---|---|---|---|---|---|
| baseline | 29 | 4 | 4 | 6 | 6 |
| tiny_faces | 74 | 38 | 38 | 38 | 39 |
| low_light | 86 | 27 | 27 | 27 | 29 |
| motion_blur | 137 | 118 | 119 | 119 | 120 |
| occlusion | 58 | 18 | 18 | 19 | 18 |
| crowd | 334 | 99 | 99 | 99 | 99 |
| late_appearance | 24 | 4 | 5 | 7 | 7 |
| edge_entry | 13 | 3 | 3 | 3 | 3 |
| erratic_motion | 87 | 44 | 45 | 45 | 45 |
| exit_reenter | 41 | 20 | 20 | 20 | 20 |
