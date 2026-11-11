# 01. Product Requirements

IDs are stable; tests and the privacy report reference them. Status: **Done / Partial / Planned**.

## Functional requirements
| ID | Requirement | Phase | Status |
|---|---|---|---|
| F1 | Detect all faces (profile, small, partial, masked) at a deliberately low threshold | 0-1 | Partial (placeholder detector) |
| F2 | Multi-face tracking: short-term plus long-term re-association | 1-2 | Partial (short-term only) |
| F3 | One persistent synthetic identity per tracked person per video | 2 | Planned |
| F4 | Replacement preserves pose, expression, gaze, lighting, skin-tone compatibility; no flicker | 2 | Planned |
| F5 | Fail-closed fallback on low confidence, lost track, budget overrun, error | 1 | Done |
| F6 | Minors: unknown age = minor, stronger default transform | 1 | Done (no age model yet) |
| F7 | Strip EXIF/GPS/XMP/container tags and re-verify the output | 1 | Done |
| F8 | Optional voice anonymization (audio dropped by default meanwhile) | 4 | Planned |
| F9 | Warn on plates, name tags, uniforms, addresses, tattoos | 4 | Planned |
| F10 | Selective body/background anonymization | 4 | Planned |
| F11 | Pre-publish review with forced pass over flagged segments | 2-3 | Planned |
| F12 | Privacy report with verification result and residual-risk statement | 1 | Done |
| F13 | Local-only; no telemetry with media or biometrics; no training on user data without opt-in | 1 | Done (no network code) |

## Non-functional requirements
| ID | Requirement |
|---|---|
| N1 | Live: <=150 ms added latency, >=24 fps at 720p, up to 3 faces on a recent flagship phone; degrade to blur beyond budget |
| N2 | Offline: >=1x real time on a laptop with GPU/NPU |
| N3 | Zero known frames with a detectable unredacted face on the benchmark set; any leak is release-blocking |
| N4 | Temp files hold only redacted frames; raw frames never touch disk |
| N5 | Deterministic policy layer, 100% branch coverage |
| N6 | All model weights license-cleared for the intended distribution (see doc 03) |

## Policy rules (implemented in `policy.py`)
1. Base treatment = BLUR.
2. Unknown or likely-minor age (prob >= 0.2) -> at least MOSAIC.
3. Ghost track (lost detection) -> at least MOSAIC.
4. Detection confidence < 0.5 -> at least MOSAIC.
5. Detector exception -> whole frame BLOCK.
6. Mean luma < 12 (detection untrustworthy) -> whole frame MOSAIC.
7. Verifier finds residual face -> BLOCK that region; still visible -> BLOCK whole frame.
8. Treatments only escalate.

## Explicit non-goals
No target-identity selection; no cloud inference; no legal guarantee.

## Acceptance criteria for "Phase 1 done"
- [x] Policy, tracking, fallback, pipeline invariants, metadata, report covered by tests (26 passing)
- [x] Whole-frame block on detector failure; ghost tracks across dropouts
- [x] Metadata verified clean on a synthetic file with GPS tags
- [ ] Real detector (BlazeFace/YuNet) benchmarked on a consented set (Phase 0 follow-up)
- [ ] Independent verifier model integrated
- [ ] Two-pass recorded-video mode closing the lookahead gap
