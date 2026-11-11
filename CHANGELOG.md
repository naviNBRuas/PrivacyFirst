# Changelog

## 0.6.0: run 006 (2026-10-22): context-identifier scan v0 + review-flow data model
- `context.py`: OCR (system Tesseract over stdin, no temp files) + rules find plate-like, contact-like (e-mail, phone, URL, handle) and
  address-like text, plus readable text and plate-shaped objects that could not be read. Identifier kinds are BLOCKed; the rest are flagged for review.
  Recognised text is never stored (not even hashed). Tracks never weaken; scan failure blocks the frame; missing engine exits 2.
- `LiveContext` (cadence, hold, lookahead backfill) and `PlannedContext` (whole-file plan: interpolation, extension, fingerprint check) feed the pipeline;
  `TwoPassRunner(context_scanner=...)`. Context regions are rendered after faces/swaps.
- `review.py`: markers coalesced from pipeline events, person/context cards, escalate-only actions, export gate, JSON round trip, overrides that
  the pipeline applies on a re-render (`face_escalations`, `context_escalations`).
- CLI: `--context-scan`, `--context-every`, `--ocr-lang`, `--review-json`. Report: keys-only `context` section, new warnings.
- `bench/contextsynth.py`, `bench/contextbench.py` (real-OCR quality + simulated temporal coverage), `scripts/demo_context.py`.
- `scripts/minipytest.py`: the offline pytest stand-in is now in the repo. Docs 16, 17, ADR 0009-0010, limitations 32-41, decisions D11-D13. 145 tests.
- Bugs found by tests/measurement during the run: overlap-only track linking split fast movers into several tracks; skipping plate-shape
  candidates inside readable text would have missed a plate on a merged OCR row (rule removed); readable sign words were flagged as unread plates.

## 0.5.0: run 005a (2026-10-22): everything that does not need model weights
- Two-pass: a dropout demotion is released after 3 consecutive detections (`swap_dropout_release_streak`, -1 = mode default: 3 in two-pass, off in live where it raised flips 5.5 -> 7.8). Swap share 59% -> 74% in the simulator; coverage unchanged. New `Track.streak`.
- `--detector haar|yunet|mediapipe` and `--model-dir` for `video` and `image`; missing weights exit 2, no silent Haar fallback.
- `bench.measure`: estimates simulator profile values from real-detector output (heuristic, no ground truth); round-trip tested.
- Negative result: exit-aware ghost expiry removed (tiny area gain, higher live leak). Doc 15 local guide. 97 tests.

## 0.4.0: run 004 (2026-10-22)
- `Tracker` rewritten: IoU + distance association, live-before-ghost, two-stage by confidence, size gate, per-frame velocity on ghost re-match (bug fix), ghost hull coverage. Old tracker kept as `LegacyIoUTracker`.
- Two-pass recorded mode (`offline.py`): geometry-only pass 1, planner (stitching, back-extension, two-sided gaps, whole-person age evidence, hindsight stability), `PlannedTracker`, fingerprint check (`PlanMismatchError`).
- CLI `video` defaults to `--mode two-pass`; `--mode live` kept. Reports gain `mode`, a two-pass section, and a live-mode warning.
- Policy: `swap_interp_max_gap` (4), `swap_sticky_dropout_frames` (15, was 30 for all reasons).
- Benchmark: `late_long` scenario, legacy-tracker and two-pass variants, swap benchmark compares three configurations and counts swap/fallback flips.
- Docs 14, ADR 0008, limitations 2/4/5/25/28 updated, 29-31 added, decision D10. 92 tests.

## 0.3.0: run 003 (2026-10-21)
- Face-change (SWAP) path behind policy gates, off by default: confidence, track stability, replacer health, identity availability, sticky demotion (30 frames), permanent demotion on recognizer failure, render-time demotion of buffered frames, budget demotion to blur, stricter minor/unknown-age path (explicit ensemble PASS + `child_ok` identity).
- `identity.py`: identity library (JSON schema, validation), deterministic stub library, collision-free persistent assignment seeing coarse bins only.
- `replace.py`: `FaceReplacer` protocol, `Replacement`, non-AI `StubReplacer`. `swapgate.py`: `SwapVerifier`, `SwapState`. `stabilize.py`: One-Euro, patch EMA, flicker metric. `blend.py`: head mask, LAB color transfer, grain, composite.
- Pipeline integration; residual-face scan ignores swapped head boxes; report gains `swap` section, per-track synthetic identity ids and demotions, new warnings.
- Swap benchmark (`bench/swapbench.py`) and stub face-change demo with preview.
- Docs 13, ADR 0006-0007, limitations 21-28, decisions D8-D9. 68 tests.

## 0.2.0: run 002 (2026-10-21)
- Project renamed to **PrivacyFirst** (package `privacyfirst`, CLI `privacyfirst`).
- Phase 0 benchmark harness: 10 synthetic hard-case scenarios with ground truth, simulated bursty detector, coverage/leak/track-ID metrics, five pipeline ablations, markdown/JSON/PNG output, `evaluate_detector()` for real detectors.
- `OutputFrame` now exposes applied regions and scene/verifier block flags for audit and benchmarking.
- MediaPipe BlazeFace and YuNet adapters (clear error when model files are missing; untested against weights).
- Docs: 11 benchmark harness, 12 identity replacement design, Phase 0 plan/MODEL_SETUP/license memo template/candidate list; ADR 0004 revised to gated photoreal for minors; limitations 16-20.
- 34 tests.

## 0.1.0: run 001 (2026-10-21)
- Phase 1 core: types, detector protocol (Haar placeholder + scripted), tracker with ghost tracks,
  policy engine, fallbacks, lookahead pipeline with backfill, verifier escalation, metadata
  stripping/verification, privacy report, CLI.
- 27 tests, synthetic demo, full documentation set (docs/00-10, ADRs 0001-0005).
- Found and fixed during the run: `encoder` stream tag surviving video re-mux (two-pass copy remux +
  `no-info=1`); misleading "verification passed" with a scripted verifier (now warned); demo exposed
  the lookahead-horizon leak (now documented and pinned by a characterization test).
