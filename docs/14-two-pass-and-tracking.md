# 14. Two-pass recorded mode and the run-004 tracker

Status: implemented in run 004 (`offline.py`, `tracking.py`). All numbers are from the **simulated** benchmark
(`runs/run-004/`): they show pipeline behaviour, not real detector accuracy.

## Why
Live mode can only look `lookahead` frames ahead, so a face first detected later than that leaves already-emitted frames
untouched (KNOWN_LIMITATIONS #2). A recorded file has no such limit. Track IDs also fragmented (#4, #19, #28), which
would give one person several synthetic faces.

## Tracker (`Tracker`, default in both modes)
`LegacyIoUTracker` (runs 001-003) stays for A/B. The new tracker:
- matches on IoU **plus** centre distance, live tracks before ghosts, high-confidence detections before low;
- widens the ghost gate with missed frames; rejects size-inconsistent matches;
- still starts a track from any unmatched detection, whatever its confidence (a miss costs more than a mask);
- **fixes a velocity bug**: a ghost re-matched after k missed frames used to take the k-frame jump as one frame of motion,
  so the next ghost overshot the face;
- a ghost now **covers the hull** of its velocity-predicted box and the last detected box (`hull_max_misses=15`), so a face
  that stopped or reversed while undetected stays covered.

What the A/B found, and what was cut. The first version of the new matching raised leak (tiny_faces 25.1% -> 32.5%,
low_light 4.8% -> 9.5%) while lowering ID changes. Ablation traced it to the velocity bug and to the loss of the old
tracker's accidental redundancy (stale duplicate ghosts covering "stopped" positions). Making that coverage explicit
(the hull) fixed it. A "revive expired track" feature showed no measured benefit and was removed.
Hull cap sweep (5 seeds, all scenarios): no hull 5.43% leak / 47.2% area; <=8 4.67% / 48.9%; **<=15 4.26% / 51.2% (chosen)**;
<=30 3.69% / 55.5%; legacy 4.61% / 50.8%. 15 is leak- and area-neutral versus run 003; 30 trades +4.3 area points for 0.6 leak points.

## Two-pass
Pass 1 keeps **geometry only** (boxes, confidences, a CRC of a 16x16 thumbnail per frame to prove pass 2 reads the same file).
Planning adds hindsight: stitch fragments up to 90 frames apart when position and size are consistent; cover up to
`back_extend=16` frames before a confirmed person's first detection (4 if seen < 3 times); fill gaps from both sides
(interpolation plus stay/keep-moving hull); apply the highest age evidence on a person to all of their frames; count
"stable" hits up to 5 frames ahead so swaps start at frame 0, not 5; allow a swap across a gap of at most
`swap_interp_max_gap=4` frames bracketed by detections. Pass 2 is the unchanged `RedactionPipeline` fed by a
`PlannedTracker`. A source that differs between passes raises `PlanMismatchError`; the CLI then writes no output (exit 3).

## Measured effect (legacy tracker + lookahead 4  ->  two-pass)
| Scenario | Leak | Redacted area | Track-ID changes |
|---|---|---|---|
| late_appearance (blind 12) | 6.9% -> 0.0% | 48.6% -> 52.8% | 5 -> 7 |
| late_long (blind 30 > back_extend) | 21.4% -> 10.7% | 50.8% -> 56.3% | 11 -> 12 |
| low_light | 4.8% -> 0.0% | 67.1% -> 73.9% | 27 -> 11 |
| motion_blur | 6.8% -> 1.2% | 65.0% -> 83.0% | 119 -> 44 |
| tiny_faces (mostly never detected) | 25.1% -> 25.6% | 34.7% -> 27.1% | 38 -> 4 |
| exit_reenter | 0.0% -> 0.0% | 43.6% -> 57.5% | 20 -> 21 |
| all scenarios | 5.83% -> 3.67% | 50.8% -> 54.0% | 389 -> 196 |

Honest reading: leak and ID changes improve broadly; **cost rises** in some scenes (motion_blur +18 points, exit_reenter +14,
from long trailing/back-extended regions); late_long still leaks because the blind period exceeds `back_extend`; tiny faces
the detector never sees are still never covered; a person who leaves and returns elsewhere is still two people (needs
appearance re-ID).

## Face-change gates (stub replacer, 3 seeds x 120 frames, defaults)
| Configuration | Swap share | Leak | Identity changes / person | Flips / 100 face-frames |
|---|---|---|---|---|
| live, legacy tracker | 40.8% | 5.77% | 1.11 | 5.5 |
| live, new tracker | 39.9% | 5.71% | 0.84 | 5.5 |
| two-pass | 59.2% | 3.84% | 0.75 | 3.5 |

Gate sweep (2 seeds x 100 frames): shortening dropout hysteresis raises swap share but also visible alternation,
concentrated in motion_blur (2.8 flips/100 at 30 frames, 11.5 at 8). **Chosen: `swap_sticky_dropout_frames=15`**
(was 30 for every reason; replacer/recognizer demotions keep 30), `swap_interp_max_gap=4`; `swap_min_track_hits` stays 5
(3 changed almost nothing). Provisional: it rests on simulated dropouts (D8).

## Not done / next
After a long outage the 15-frame dropout hysteresis keeps a person on mosaic for 15 frames after re-detection
(visible in the demo); two-pass could end it early. Trailing ghosts after a face exits the frame cost area; an
exit-aware expiry needs its own coverage test. Appearance re-ID for returning people. Real detector data for everything.
