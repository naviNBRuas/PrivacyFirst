# Privacy Report: two-pass demo (drawn faces, STUB replacer)

- Generated: 2026-10-22T00:09:44+00:00  |  Tool v0.3.0
- Detector: scripted [two-pass replay]
- Frames: 84 in / 84 out
- Faces/tracks redacted: 2
- Verification: **not_run** (0 frames scanned, 0 escalations, 0 unresolved/blocked)
- Minor exception used: False

## Warnings
- Stub replacer in use: the output is a cartoon stand-in, NOT an AI face change.
- Unvetted identity library in use: identities have not passed offline vetting.

## Tracks

| Track | Frames | Ghost | Treatments | Minor-risk |
|---|---|---|---|---|
| 1 | 0-83 (84) | 35 | {'swap': 35, 'mosaic': 49} | True |
| 2 | 0-83 (84) | 14 | {'mosaic': 28, 'swap': 56} | True |

## Fallback reasons

- face_detected: 168
- ghost_track: 49
- minor_or_unknown_age: 77
- swap_gate:ghost_track: 49
- swap_gate:minor_gate_not_passed: 28
- swap_gate:sticky_demotion: 75
- swap_gate:track_not_stable: 14
- swap_gate_passed: 91

## Two-pass analysis (geometry only, no pixels kept)
- Tracklets 3 merged into 2 people (1 stitches)
- Frames covered before first detection: 14 | interpolated gap frames: 35 | trailing ghost frames: 0

## Face change (swap)
- Replacer: stub-replacer (NOT AI) (stub: True)
- Region-frames swapped: 91 | demoted at render: 0
- Demotions by reason: {'ghost_track': 49, 'track_not_stable': 14, 'minor_gate_not_passed': 28, 'sticky_demotion': 75}
- Identity assignments: 2 (unvetted library: True)
- Recognizer check: 20 checks, 0 failures; recognizers: recognizer-A (sim), recognizer-B (sim)

## Metadata
- Verified clean: **True**
- GPS before/after: False / False
- Tag keys removed: encoder
- Audio dropped: True

## Not covered
- Context identifiers (plates, name tags, addresses, tattoos): not implemented in Phase 1

## Notice
Faces are redacted by blur/mosaic/block unless the face-change path is enabled with a real replacer. The only replacer in this build is a non-AI stub. Voice is not anonymized (audio is dropped by default).

## Residual risk
Face replacement and redaction reduce privacy risk but do not by themselves guarantee anonymization under any law or regulation. People can still be identified from other cues: voice, body, clothing, tattoos, location, background, text, and surrounding context. Verification passing means the tested recognizers did not match; it is not proof that no recognizer, present or future, could.
