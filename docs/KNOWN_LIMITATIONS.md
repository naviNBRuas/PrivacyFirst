# Known Limitations (updated run 006)

Read this before trusting any output. Each item says what breaks, why, and what closes it.

| # | Limitation | Consequence | Closed by |
|---|---|---|---|
| 1 | **Placeholder detector** (OpenCV Haar) | Misses many real faces (angle, light, small, masked) | Phase 0/1: BlazeFace or YuNet, benchmarked |
| 2 | **Late first detection beyond the lookahead** (**partly closed, run 004**) | LIVE mode still leaks earlier frames (pinned by `test_KNOWN_LIMIT_*`; reports warn). Two-pass covers up to `back_extend`=16 frames before a first detection; a longer blind period still leaks (`late_long`: 10.7%, pinned by a test) | Longer/adaptive back-extension, better detector |
| 3 | **CLI verifier = same model as the detector** | "Passed" is nearly vacuous; the report warns because the detector is a placeholder | Independent verifier from a different model family |
| 4 | **Tracker is still simple** (improved run 004: two-stage matching, offline stitching) | ID switches in crossings remain (crowd 62 changes); a person who leaves and returns elsewhere is a new person | Appearance re-ID; real-footage tuning |
| 5 | **Linear ghost prediction** (mitigated run 004) | Ghosts now cover the hull of stayed/kept-moving for 15 frames; longer outages and sharper manoeuvres can still escape | Better motion model; verifier |
| 6 | **No age model** | Everyone is treated as a possible minor (mosaic) in strict profile | Calibrated, over-flagging age bucket in Phase 4 |
| 7 | **Blur is weaker than mosaic/block** | Standard profile uses blur for known adults; deblurring attacks are conceivable | Strict default; consider mosaic-only; test against deblurring |
| 8 | **Scene check is luma-only** | Motion blur, glare, lens obstruction are not detected | Scene-quality scoring |
| 9 | **No voice anonymization** | Audio is dropped by default; if kept, report flags it | Phase 4 |
| 10 | **Context scan is v0 and off by default** (run 006, docs/16) | Plates, phone numbers, e-mails, addresses are found by OCR + rules; name tags, uniforms, logos, tattoos, QR codes are not scanned at all | Real-footage calibration; detectors for the rest |
| 11 | **Metadata verification = ffprobe tags** | Exotic container atoms not exposed by ffprobe could evade the check | Add binary-level scan for known atoms/XMP packets; fuzz corpus |
| 12 | **Orientation/rotation side data** | OpenCV may ignore rotation metadata, changing orientation | Handle display-matrix explicitly; add test |
| 13 | **Python, CPU only** | Not real-time | C++/Rust + ONNX Runtime/CoreML, Phase 3 |
| 14 | **Lossy re-encode** | Quality loss from mp4v then x264 | Single-pass encode with a hardware encoder |
| 15 | **No photoreal swap, no guardian gate, no review UI** | Phase 1 scope | Phases 2-4 |

| 16 | **The AI face change is not real yet** (gates built, stub replacer only) | Real output today is blur/mosaic/block; a stub cartoon face when swap is enabled | Phase 2 (docs/12, 13) |
| 17 | **Benchmark uses a simulated detector on drawn faces** | Shows pipeline behaviour, not real accuracy; area-cost figures inflated by scene scale | Real footage + real detectors (Phase 0 task 3-4) |
| 18 | **Real-model adapters untested against weights** | Could fail at runtime on first real use | Local smoke check (docs/phase0/MODEL_SETUP.md) |
| 19 | **Track IDs fragment** in motion blur and crowds (measured in run 002) | A person could receive more than one synthetic identity in Phase 2 | ByteTrack/OC-SORT + re-ID; offline tracklet clustering |
| 20 | **Never-detected faces cannot be recovered** (tiny faces leak even with ghost tracks and lookahead 16) | Safety net is bounded by the detector | Better detector, upscaling pass, person-detector fallback |

| 21 | **The only replacer is a non-AI stub** (flat cartoon face; no expression, gaze, or pose) | The face-change path is proven for gating/bookkeeping, not for realism | Real swap backend (run 005) |
| 22 | **Head mask is an ellipse, not segmentation** | Hair, ears, and neck outside the ellipse stay original; identity cues can remain. Benchmarks count the whole head box as covered for swap regions, which is only true with a real replacer and a passing verifier | Face-parsing/matting model |
| 23 | **Swap verification is patch-level and sampled** (original crop vs generated patch, every 5 frames) | The composited output is not re-verified; frames between checks rely on the last result | Output-level re-check; adaptive sampling on anomalies |
| 24 | **Recognizers are stubs; thresholds uncalibrated** (0.35 adult / 0.20 minor are placeholders) | A "pass" means nothing about real recognizers yet | Real ensemble + calibration on consented data |
| 25 | **Swap share vs alternation is tuned on a simulator only** (run 004/005: dropout hysteresis 30 -> 15, interpolation gap 4, two-pass early release after 3 detections; swap share 74% two-pass / 40% live) | May feel wrong on real detectors; 15 frames of mosaic still follow every outage | Real-footage calibration (kit: docs/15) |
| 26 | **Identity pool exhaustion and crude tone bins** (crowds hit `no_identity`; luma-based tone bin is lighting-sensitive) | Demotions in crowds; potential bias across skin tones | Larger vetted library; better bins; fairness testing |
| 27 | **No landmarks or pose estimation** | Replacer health and the pose gate are stubs | Landmark model (e.g. MediaPipe Face Landmarker) |
| 28 | **A returning person may get a new identity** (two-pass stitches fragments close in space; motion_blur 119 -> 44 ID changes, not zero; exit/re-enter elsewhere unchanged) | One person, several synthetic faces | Appearance re-ID |

| 29 | **Two-pass costs area** (motion_blur 65% -> 83%, exit_reenter 44% -> 58% of frame; back-extension and long trailing ghosts) | More of the picture is hidden than strictly needed | Tried exit-aware ghost expiry in run 005: saved only 0.4-1.8 area points and raised live leak (motion_blur 1.1% -> 1.9%), so it was removed. Most extra area is back-extension and hulls, not trailing ghosts |
| 30 | **Two-pass needs the whole file twice** and a stable source | Slower; a changed file aborts with no output (by design) | Streaming-safe chunked planning |
| 31 | **Test runs in the sandbox used a mini-runner**, not pytest (no network); it is now `scripts/minipytest.py` | Run `python -m pytest -q` locally to confirm | n/a |

## What this build can honestly claim
It reliably applies destructive redaction wherever its detector or ghost/backfill logic finds a face,
fails closed on errors, strips metadata it can enumerate, and reports what it did. It **cannot**
claim that every face in real footage was found, or that people are not identifiable.

| 32 | **OCR only finds what it can read** (measured, synthetic: 94% of identifiers, 85% of plates covered in the default config; clean-font plates 75%; 25-degree rotated e-mail 50%) | Small, blurred, rotated, stylised, upside-down or non-English text and plates are missed; real plates are harder than rendered fonts | Real-footage calibration; better plate/text models; install language packs |
| 33 | **Scan cadence** (default every 3rd frame) | An item visible for fewer frames than the cadence can be missed entirely (6-frame pass, cadence 8: 25% leak even with a perfect scanner) | `--context-every 1`; decision D12 |
| 34 | **No independent verifier for context** | Re-OCRing the output returned nothing even for a visible sign, so "OCR found nothing" is weak evidence | A different-family text detector as verifier |
| 35 | **Axis-aligned boxes** | Rotated text hides a lot of blank area (14% of the frame at 10 degrees, 24% at 25 in the synthetic set) | Quad/polygon regions |
| 36 | **Ordinary text is flagged, not redacted** (ADR 0009, D11) | A sign can still carry location or school cues until the reviewer decides | `text_treatment=MOSAIC` or the review step |
| 37 | **Pattern sets are English/Portuguese-leaning and heuristic** | Other address/phone/plate formats are missed; plate-like words such as "iPhone15" are blocked (over-redaction) | Locale packs, calibration |
| 38 | **Context scan is CPU-heavy** (0.54 s per 800x560 frame on one core, plus crops; 1080p untested) | Slow on long files at cadence 1 | Native OCR engines, GPU, region-of-interest scanning |
| 39 | **Review model has no relax/dismiss and no UI** (ADR 0010, D13) | A false positive cannot be un-redacted without a re-run; verifier failures are not mapped to tracks, so any minor-risk person turns a failed verification into a hard block | Guardian gate, per-track verifier mapping |
| 40 | **Context benchmark is synthetic** (invented text, clean fonts, 4 scenes per variant: cells are multiples of 25%) | Optimistic and noisy; says nothing about real footage | Labelled real clips |
| 41 | **Plate-shape finder is tuned on drawn rectangles** | Real frames have many more rectangles (windows, signs): expect more unread-shape flags and a slower scan | Calibration on real footage |
