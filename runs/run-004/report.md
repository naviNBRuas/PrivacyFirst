# Privacy Report: synthetic_demo (drawn faces, no real people)

- Generated: 2026-10-22T05:00:37+00:00  |  Tool v0.4.0
- Detector: scripted
- Frames: 48 in / 48 out
- Faces/tracks redacted: 2
- Verification: **passed** (48 frames scanned, 0 escalations, 0 unresolved/blocked)
- Minor exception used: False

## Warnings
- Verifier 'scripted' is a placeholder/scripted stand-in: a 'passed' result is NOT meaningful.
- Live mode: a face first detected more than the lookahead after it appeared can leave earlier frames unredacted (use two-pass mode for recorded files).

- Verifier: scripted

## Tracks

| Track | Frames | Ghost | Treatments | Minor-risk |
|---|---|---|---|---|
| 1 | 0-47 (48) | 8 | {'blur': 40, 'mosaic': 8} | False |
| 2 | 0-47 (45) | 0 | {'blur': 41, 'mosaic': 4} | False |

## Fallback reasons

- backfill: 3
- face_detected: 93
- ghost_track: 8
- low_confidence: 4

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
