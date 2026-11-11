# Run Log

One entry per run. Each run ends with: tests green, demo regenerated, zip + preview delivered.

## Run 001: Phase 1 core + documentation foundation
**Date:** 2026-10-21 | **Artifacts:** `runs/run-001/` (preview.png, preview.gif, demo_redacted.mp4, report.md/json, test_output.txt)

**Built**
- Pipeline core: detector protocol, ghost-track tracker, policy engine, destructive fallbacks, lookahead buffer with backfill, verifier escalation, metadata stripping/verification, privacy report, CLI.
- Docs 00-10, five ADRs, known limitations, open decisions.
- Tests: 27 passing (policy, tracking, fallback, pipeline invariants, metadata, no-network).

**Found during the run (and what changed)**
1. Metadata verifier caught a surviving `encoder` stream tag -> two-pass copy remux and `no-info=1`.
2. Demo preview exposed a real leak: a face first detected beyond the 4-frame lookahead left earlier frames unredacted -> documented (KNOWN_LIMITATIONS #2), pinned with a characterization test, demo rescoped so backfill is shown within its horizon. Real fix = Phase 1b two-pass.
3. Report said "verification passed" with a scripted verifier -> report now names the verifier and warns when it is placeholder/scripted.

**Not done (by design, next runs)**: real detector/verifier models, two-pass recorded mode, photoreal swap, age model, voice, context scan, review UI, benchmark harness.

**Decisions needed from you:** see `docs/OPEN_DECISIONS.md` (D1 platform, D2 minors transform, D3 distribution/licensing are the blockers for Phase 0/2).

**Suggested next run:** Run 002 = Phase 0 benchmark harness (recall@FPPI, latency, synthetic hard cases, license memo template), then Run 003 = two-pass recorded mode.

## Run 002: Phase 0 benchmark harness + identity-replacement design
**Date:** 2026-10-21 | **Artifacts:** `runs/run-002/` (benchmark.md/json, benchmark_leak_rate.png, demo preview, report, test_output.txt)

**Direction change from the founder:** redaction should be an AI change of facial features (a natural face remains), not blur. Captured in docs/12 and ADR 0004; Phase 1 blur/mosaic/block is the fail-closed safety net underneath.

**Built:** project rename; benchmark harness (10 scenarios, simulated detector, coverage metrics, ablations); region/audit exposure on `OutputFrame`; MediaPipe/YuNet adapters; Phase 0 plan, MODEL_SETUP, license memo template, candidate CSV; docs 11 and 12; 34 tests.

**Findings from the benchmark (simulated detector, see doc 11):** ghost tracks recover most correlated dropouts; never-detected faces (tiny) still leak; late appearance needs lookahead >= blind period (two-pass mode needed); over-redaction cost rises with ghost/lookahead; track IDs fragment in motion blur/crowds.

**Blocked by environment:** real model weights are unreachable from the sandbox (YuNet is a Git-LFS pointer on GitHub raw; MediaPipe pip no longer bundles a model; face-swap weights live on hosts not on the allowlist). Adapters are written but untested; allow the hosts or run locally to unblock run 005.

**Next:** Run 003 = SWAP gates in policy, `FaceReplacer` protocol + stub, identity library + assignment, head mask/blend, flicker metric.

## Run 003: face-change gates, identity library, stabilization, stub replacer
**Date:** 2026-10-21 | **Artifacts:** `runs/run-003/` (swap_preview.png/.gif, demo_swap.mp4, swap_report.md/json, swap_benchmark.md/json, run-002 benchmark refresh, test_output.txt)

**Built:** the whole face-change path around a replacer interface, with a non-AI stub so it is testable without weights (docs/13, ADR 0006-0007); 68 tests.

**Findings (stub replacer + simulated detector, 3 seeds x 120 frames):**
- One persistent identity per person cuts flicker roughly 3-4x versus re-picking every frame (about 5-8 vs 18-22).
- No identity collisions in any scenario; crowds exhaust the identity pool (`no_identity` demotions).
- Conservative gates leave only ~44% of baseline face-frames as swap (ghost tracks, 30-frame hysteresis, 5-frame stability): tune in run 004.
- Track fragmentation gives one person several identities (about 4.2 changes per person in motion blur): tracker upgrade is the next blocker.
- Leak rates with swap enabled are comparable to run 002's ghost+look4 results (within about 1-2 points; the benchmarks use different seed sets), so enabling swap did not visibly weaken coverage.

**Mistakes caught during the run:** the first demo's scripted verifier failure hit the wrong face because skipped checks shifted a call counter; the demo's face drifted off-frame past frame ~50. Both fixed; one test expectation (transition count) was my arithmetic, not a bug.

**Still blocked:** real model weights unreachable from the sandbox. **Next:** run 004 = tracker upgrade (ID stability), two-pass recorded mode, gate tuning.

## Run 004: tracker upgrade, two-pass recorded mode, gate tuning
**Date:** 2026-10-22 | **Artifacts:** `runs/run-004/` (benchmark.md/json/png, swap_benchmark.md/json, two_pass_preview.png/.gif, demo_two_pass.mp4, two_pass_report, two_pass_demo_summary.json, test_output.txt)

**Built:** new `Tracker` (legacy kept for A/B), `offline.py` two-pass mode, CLI `--mode`, report mode/warnings, `late_long` scenario, benchmark variants, swap flip metric; docs 14, ADR 0008; 92 tests. Details in docs/14.

**Findings (simulated detector, so pipeline behaviour not real accuracy):**
- Two-pass vs legacy tracker + lookahead 4: leak 5.83% -> 3.67%, track-ID changes 389 -> 196, mean redacted area 50.8% -> 54.0%. Late appearance (blind 12 frames) 6.9% -> 0.0%; blind 30 frames still 10.7%.
- Cost is real: motion_blur area 65% -> 83%, exit_reenter 44% -> 58%.
- Tiny never-detected faces are unchanged (25%): no tracker fixes a face nothing sees.
- Swap share at default gates: 40.8% (live, legacy) / 39.9% (live, new) / 59.2% (two-pass).

**Mistakes caught during the run:**
1. My first tracker raised leak (tiny_faces 25.1% -> 32.5%). Ablation found a velocity bug on ghost re-match (k-frame jump taken as one frame; the old tracker had it too, rarely hit) and lost accidental redundancy from duplicate ghosts. Fixed the bug and made the coverage explicit (hull). A revive feature with no measured benefit was deleted.
2. A test caught back-extension stopping at 15 frames when 16 was configured.
3. A Python edit run from inside `src/privacyfirst` failed silently (the package's `types.py` shadowed the stdlib) and I briefly read "68 passed" as meaning the change was applied; re-ran and verified by grep.
4. The first demo summary implied identity changes in live mode; the data showed the deterministic assigner reused the identity, so the banner and docstring were corrected.
5. My first gate sweep timed out (churn counterfactual in every config); the background sweep died silently; reran in the foreground.

**Caveats:** pytest could not be installed offline, so the suite was run with a small compatible runner (see limitation 31): please run `python -m pytest -q` locally. `demo_swap`/`demo_synthetic` were regenerated into run-004 under the new defaults. Gate values remain provisional (D8, D10).

**Still blocked:** real model weights unreachable from the sandbox. **Next:** run 005 = real detector/replacer/recognizers (needs allowlisted hosts or a local run); then end hysteresis early in two-pass, exit-aware ghost expiry, appearance re-ID.

## Run 005a: the part of run 005 that needs no model weights
**Date:** 2026-10-22 | **Artifacts:** `runs/run-005/` | **Not done:** the real-model run itself. The sandbox has no network and no face weights (checked: no outbound access; only unrelated .onnx files on disk), so no real detector, replacer or recognizer was run and nothing here measures real accuracy.

**Built:** early release of dropout demotions (`streak`), `--detector`/`--model-dir`, `bench.measure`, docs/15, 5 new tests (97 total).
**Measured (simulator):** release after 3 detections: two-pass swap share 59.2% -> 73.7%, flips/100 3.5 -> 4.0, identity changes/person 0.75 -> 0.89, leak/area/ID-change tables unchanged. In live mode the same release raised flips 5.5 -> 7.8, so it stays two-pass only. Costs worth knowing: more swapped frames means more exposure to identity changes; swap quality is still unmeasured (stub replacer).
**Negative result:** exit-aware ghost expiry saved 0.4-1.8 area points, live leak got worse (motion_blur 1.1% -> 1.9%); removed.
**Caveats:** pytest still unavailable offline (mini-runner, run `python -m pytest -q` locally). `bench.measure` and the YuNet/MediaPipe adapters have never seen real footage. Tests for `measure` only verify a round trip on simulator output.
**Next (you):** follow docs/15 with real weights and footage; send back `measured.json` and I will recalibrate D8/D10 with it.

## Run 006: context-identifier scan v0 and review-flow data model
**Date:** 2026-10-22 | **Artifacts:** `runs/run-006/` (context_benchmark.md/json, demo_context.mp4, context_preview.png, context_report.md/json, review_session.json, context_demo_summary.json, test_output.txt)

**Environment change worth knowing:** Tesseract 5.3.4 (English data only) is installed in the sandbox, so this run measured **real OCR**, on synthetic text. Face weights are still unavailable (run 005b is still pending). pytest still cannot be installed; `scripts/minipytest.py` is now in the repo.

**Built:** `context.py` (OCR over stdin, classification, plate-shape finder, tracks, live source, two-pass plan), pipeline/offline/report/CLI integration, `review.py`, synthetic scene generator + benchmark, demo, docs 16-17, ADR 0009-0010, limitations 32-41, decisions D11-D13. Tests 97 -> 145.

**Measured (synthetic, optimistic; docs/16):** default engine covers 94% of identifiers and 85% of plates at 0.54 s/frame on one core; whole-frame OCR alone covers 71% / 33% (psm 6) or 80% / 48% (psm 6+3), so the plate-shape finder is what makes plates workable. A 4-pass "thorough" engine costs 1.8x for no gain. Temporal logic: the two-pass extension cuts leak at cadence 3 with 30% scan misses from 13.9% to 0.8%; a pass shorter than the cadence can be missed outright.
**Demo:** plate and phone fully covered (60/60 and 42/42 frames) in live and two-pass; the clip does not separate the modes. A reviewer's escalation of the flagged sign takes it from 0/60 to 60/60 on re-render; 4 markers, 2 decisions.

**Mistakes and surprises caught during the run:**
1. Sparse-text OCR (`psm 11`) read almost nothing except big signs; my first experiment also scored combined passes wrongly (duplicated text), so I rescored per pass. A "stack the crops into one image" speed-up failed because Tesseract skips bright bordered rectangles in a montage.
2. My first synthetic layout overlapped items, which would have corrupted ground truth; and my first coverage metric scored against the whole plate patch rather than the characters. Both fixed.
3. Overlap-only track linking split a fast-moving plate into three tracks (found by a unit test); centre-distance fallback added.
4. I added a rule skipping plate-shape candidates inside readable text to cut false flags; the real-OCR test showed it would miss a plate on a row OCR had merged with a sign. Rule removed; the flags were cut with a safer threshold instead (demo 6 flags -> 1).
5. Re-OCRing the redacted output found nothing even for the visible sign: so "OCR found nothing" cannot serve as a verifier (limitation 34).
6. The temporal benchmark's first scenarios were aligned with the scan cadence and flattered the result; timing is now shifted per seed.

**Caveats:** all context numbers use invented text in clean fonts (4 scenes per variant, cells are multiples of 25%); real plates and footage are unmeasured. Single CPU core, so crop-level parallelism was never exercised. Please run `python -m pytest -q` locally.
**Decisions needed from you:** D11 (redact or only flag ordinary text), D12 (default-on and cadence), D13 (review interpretations, docs/17).
**Next (you):** real footage with real plates would let me calibrate patterns, cadence and the plate-shape finder (limitations 32, 37, 41). Otherwise run 005b (real weights) or the candidates in docs/07.
