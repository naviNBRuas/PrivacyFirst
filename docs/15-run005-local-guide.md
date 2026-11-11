# 15. Run 005 local guide: what needs real models, and how to do it

The sandbox has no network and no face-model weights, so the real-model part of run 005 could not be done there and
nothing in this repo claims real-detector accuracy. Everything below runs on your machine.

## 1. Get weights (you choose and license-check them)
Follow `docs/phase0/MODEL_SETUP.md` (YuNet or MediaPipe detector files) and `docs/phase0/license-clearance-memo-TEMPLATE.md`.
Put files in one directory and either pass `--model-dir DIR` or set `PRIVACYFIRST_MODEL_DIR`. If a file is missing the CLI
exits 2 with the instruction; it never falls back to Haar silently.

## 2. Check the adapters work
`privacyfirst video clip.mp4 out.mp4 --detector yunet --model-dir DIR` (adapters were written in run 003 and have never run
against real weights; expect to fix small API mismatches).

## 3. Measure the detector on your footage (replaces guessed simulator values)
`python -m privacyfirst.bench.measure clip1.mp4 clip2.mp4 --detector yunet --model-dir DIR --out measured.json`
It reports confidence and face-size quantiles, miss-burst rate and length, and a false-positive upper bound in the
`DetectorProfile` vocabulary. They are heuristics without ground truth (occlusions count as misses): spot-check a few
bursts by eye, then put the values into `DetectorProfile` in `bench/synth.py` and rerun both benchmarks.

## 4. Then, in this order
1. Re-sweep `swap_sticky_dropout_frames`, `swap_dropout_release_streak`, `swap_interp_max_gap` (D8) and the ghost hull cap (D10) with measured profiles.
2. Plug a real replacer and recognizers behind `Replacer` / `FunctionRecognizer`; calibrate recognizer thresholds (0.35 adult / 0.20 minor are placeholders).
3. Label a small real set (faces per frame is enough) to turn the heuristic leak estimate into a measured one.

## Do not
Claim anonymization from any of this; the stub replacer and the simulator prove gating and bookkeeping only.
