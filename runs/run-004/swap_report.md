# Privacy Report: swap demo (drawn faces, STUB replacer)

- Generated: 2026-10-22T05:00:38+00:00  |  Tool v0.4.0
- Detector: scripted
- Frames: 72 in / 72 out
- Faces/tracks redacted: 2
- Verification: **not_run** (0 frames scanned, 0 escalations, 0 unresolved/blocked)
- Minor exception used: False

## Warnings
- Stub replacer in use: the output is a cartoon stand-in, NOT an AI face change.
- Unvetted identity library in use: identities have not passed offline vetting.
- Live mode: a face first detected more than the lookahead after it appeared can leave earlier frames unredacted (use two-pass mode for recorded files).

## Tracks

| Track | Frames | Ghost | Treatments | Minor-risk |
|---|---|---|---|---|
| 1 | 0-71 (72) | 8 | {'mosaic': 26, 'swap': 46} | True |
| 2 | 0-71 (72) | 0 | {'mosaic': 36, 'swap': 36} | True |

## Fallback reasons

- face_detected: 144
- ghost_track: 8
- minor_or_unknown_age: 58
- swap_gate:ghost_track: 8
- swap_gate:minor_gate_not_passed: 36
- swap_gate:sticky_demotion: 49
- swap_gate:track_not_stable: 8
- swap_gate:verification_failed: 28
- swap_gate_passed: 86

## Face change (swap)
- Replacer: stub-replacer (NOT AI) (stub: True)
- Region-frames swapped: 82 | demoted at render: 4
- Demotions by reason: {'track_not_stable': 8, 'minor_gate_not_passed': 36, 'ghost_track': 8, 'sticky_demotion': 49, 'verification_failed': 28}
- Identity assignments: 2 (unvetted library: True)
- Recognizer check: 19 checks, 1 failures; recognizers: recognizer-A (scripted), recognizer-B (scripted)

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
