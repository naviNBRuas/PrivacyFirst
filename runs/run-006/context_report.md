# Privacy Report: demo_context.mp4

- Generated: 2026-10-23T06:03:35+00:00  |  Tool v0.6.0
- Detector: scripted [two-pass replay]
- Frames: 60 in / 60 out
- Faces/tracks redacted: 0
- Verification: **not_run** (0 frames scanned, 0 escalations, 0 unresolved/blocked)
- Minor exception used: False

## Warnings
- Context scan is heuristic OCR (v0): text that is small, blurred, rotated, stylised, upside down or not in the installed OCR languages is NOT found, and name tags, uniforms, logos and tattoos are never scanned.
- Context scan ran on every 3th frame: an item visible for fewer frames between scans can be missed.

## Tracks

| Track | Frames | Ghost | Treatments | Minor-risk |
|---|---|---|---|---|

## Fallback reasons


## Two-pass analysis (geometry only, no pixels kept)
- Tracklets 0 merged into 0 people (0 stitches)
- Frames covered before first detection: 0 | interpolated gap frames: 0 | trailing ghost frames: 0

## Metadata
- Verified clean: **True**
- GPS before/after: False / False
- Tag keys removed: encoder
- Audio dropped: True

## Context identifiers (scan v0, heuristic OCR; recognised text is never stored)
- Engine: tesseract (languages: eng), scan every 3 frame(s), two_pass mode
- Frames scanned: 20 | scan failures (frames blocked): 0
- Regions by kind: {'plate_like': 1, 'plate_shape_unread': 1, 'text': 1, 'contact_like': 1}
- Redacted: 4 region(s), 173 region-frames | flagged only (pixels untouched, needs review): 0 region(s), 0 region-frames
- Reviewer escalations applied: 66

## Not covered
- Context identifiers (plates, name tags, addresses, tattoos): scan v0 ran (heuristic OCR; see warnings). Name tags, uniforms, logos and tattoos are never scanned

## Notice
Faces are redacted by blur/mosaic/block unless the face-change path is enabled with a real replacer. The only replacer in this build is a non-AI stub. Voice is not anonymized (audio is dropped by default).

## Residual risk
Face replacement and redaction reduce privacy risk but do not by themselves guarantee anonymization under any law or regulation. People can still be identified from other cues: voice, body, clothing, tattoos, location, background, text, and surrounding context. Verification passing means the tested recognizers did not match; it is not proof that no recognizer, present or future, could.
