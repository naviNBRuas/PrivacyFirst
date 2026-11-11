# PrivacyFirst

Local-first, **fail-closed** face redaction for video and images, built to protect people's
identities, especially children, before footage is recorded or shared.

> **Status: Phase 1 core + benchmark harness + face-change gates with a stub generator + two-pass recorded mode (run 004) + context-identifier scan v0 and review data model (run 006).** Detection interface, tracking with ghost tracks, a
> deterministic policy engine, blur/mosaic/block redaction, lookahead buffering with backfill,
> residual-face verification hooks, metadata stripping, and a privacy report all work and are tested.
> **Photoreal synthetic face replacement is NOT implemented yet** (Phase 2), and the bundled
> detector is a **placeholder** (OpenCV Haar) for plumbing only. Do not use this build to make
> real privacy claims about real footage. See `docs/KNOWN_LIMITATIONS.md`.

## What it does today
| Capability | State |
|---|---|
| Face detection (pluggable interface) | Interface done; Haar placeholder only |
| Multi-face tracking, stable IDs, ghost tracks over detector dropouts | Done (run 004: two-stage tracker, ghost hull coverage; still no appearance re-ID) |
| **Detector measurement kit** (`bench.measure`, `--detector`, docs/15) | Done, never run on real weights |
| **Two-pass recorded mode** (whole-file analysis, backward coverage, fragment stitching) | **Done (run 004)**, default for `privacyfirst video`; blind periods longer than 16 frames still leak |
| Deterministic policy engine (minors-by-default, low-confidence escalation, scene fail-closed) | Done |
| Blur / mosaic / block region treatments | Done |
| Lookahead buffer + backfill of late detections | Done (bounded by lookahead; see limitations) |
| Residual-face verifier with escalation and whole-frame block | Done (needs a real, independent verifier model) |
| Metadata stripping + verification (video, image), audio dropped by default | Done |
| Privacy report (JSON + Markdown), keys-only, no biometric payload | Done |
| Phase 0 benchmark harness: synthetic hard cases, leak/coverage metrics, pipeline ablations | Done (run 002) |
| Real detector adapters (MediaPipe BlazeFace, YuNet) | Written; **untested against real weights** (model files not bundled) |
| Face-change path: swap gates, synthetic identity library + collision-free assignment, smoothing, blending, recognizer-ensemble verification, sticky demotion | **Done with a non-AI stub replacer** (docs/12, 13). Off by default |
| **Real AI face change** (real swap model, real recognizers) | **Not yet** (needs model weights; run 005). Blur/mosaic/block is the safety net |
| **Context-identifier scan v0** (plates, phone, e-mail, address via OCR; `--context-scan`, doc 16) | Done (run 006), heuristic, off by default, measured on synthetic text only |
| **Review-flow data model** (markers, escalate-only actions, export gate, `--review-json`, doc 17) | Done (run 006), no UI |
| Voice anonymization, guardian gate, review UI | Not yet (Phases 3-4) |

## Quick start
```bash
pip install -e ".[dev]"          # needs ffmpeg + ffprobe on PATH
python -m pytest -q              # 145 tests (offline: python scripts/minipytest.py)
python scripts/demo_two_pass.py runs/demo-2pass  # live vs two-pass side by side
python -m privacyfirst.bench --out runs/bench   # Phase 0 benchmark (simulated detector failures)
python -m privacyfirst.bench.swapbench --out runs/bench   # face-change gates benchmark (stub replacer)
python scripts/demo_swap.py runs/demo-swap       # stub face-change demo with preview
python scripts/demo_context.py runs/demo-context # plate/phone/sign demo (needs tesseract)
python -m privacyfirst.bench.contextbench --out runs/bench   # context scan benchmark
python scripts/demo_synthetic.py runs/run-001   # synthetic demo -> preview.png/.gif, report
privacyfirst video in.mp4 out.mp4 --report-md report.md --report-json report.json   # two-pass by default
privacyfirst video in.mp4 out.mp4 --mode live   # streaming-style, bounded lookahead (reports warn)
privacyfirst video in.mp4 out.mp4 --context-scan --review-json review.json   # also scan for plates, phone numbers, addresses
privacyfirst image in.jpg out.png
```
Defaults are strict: **unknown age is treated as a minor** (mosaic), audio is dropped, and any
detector error blocks the frame. `--profile standard` relaxes only the unknown-age rule.

## Repository map
```
src/privacyfirst/   types, detect, tracking, policy, fallback, pipeline, metadata, report, cli
tests/          policy, tracking, fallback, pipeline invariants, metadata, benchmark, adapters
scripts/        demo_synthetic.py, package.sh
docs/           product, architecture, models, threat model, safety, UX, roadmap, tests, legal
docs/adr/       architecture decision records
runs/           per-run outputs (preview, report, test log)
```
Start with `docs/12-identity-replacement-design.md` (the AI face change) and `docs/13-swap-gates-and-identity-library.md`, `docs/00-vision-and-scope.md`, then `docs/02-architecture.md`, then `docs/RUN_LOG.md`.

## Design rules that never change
1. Raw frames, crops, and embeddings stay in RAM on the user's device. No network code exists.
2. Treatments only escalate (blur < mosaic < block). No code path downgrades to "unredacted".
3. Any uncertainty (detector error, low confidence, dropout, dark scene, verifier failure) redacts more, never less.
4. Reports contain counts and key names only: no faces, no embeddings, no metadata values.
5. The tool never claims legal anonymization.
