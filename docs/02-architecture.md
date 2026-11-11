# 02. Architecture

## Data flow
```
Camera/file
  -> frame ring buffer (RAM only, N-frame lookahead)
  -> detector (low threshold) -> tracker (+ghost tracks) -> policy engine
  -> region treatments (blur/mosaic/block; swap in Phase 2) -> compositor
  -> verifier (independent detector) -> escalate or block
  -> encoder (redacted frames only) -> metadata sanitizer -> privacy report
```

## Modules (`src/privacyfirst/`)
| Module | Responsibility | Notes |
|---|---|---|
| `types.py` | Box, Detection, Treatment ordering, Decision | `stronger()` enforces escalate-only |
| `detect.py` | `Detector` protocol, Haar placeholder, scripted test detector | Swap in BlazeFace/YuNet via the same protocol |
| `tracking.py` | IoU + velocity tracker, ghost tracks | Phase 2: ByteTrack/OC-SORT + ephemeral re-ID |
| `policy.py` | Deterministic rules: track/scene -> treatment | No ML; fully unit-tested |
| `fallback.py` | Destructive region treatments | SWAP unimplemented -> BLOCK |
| `pipeline.py` | Lookahead buffer, backfill, render, verify, stats | Core invariant lives here |
| `metadata.py` | ffmpeg/ffprobe/Pillow stripping and verification | Keys only in outputs |
| `report.py` | Privacy report JSON/Markdown | No pixels, embeddings, or values |
| `cli.py` | `privacyfirst video|image` | Temp dir holds only redacted frames |
| `identity.py` | Synthetic identity library (JSON schema), tone bins, collision-free persistent assignment | Coarse bins only (ADR 0007) |
| `replace.py` | `FaceReplacer` protocol, `Replacement`, non-AI `StubReplacer` | Real model plugs in here |
| `swapgate.py` | `SwapVerifier` (recognizer ensemble), `SwapState` | Fails closed |
| `stabilize.py`, `blend.py` | One-Euro, patch EMA, flicker metric; head mask, color/grain match, composite | |
| `context.py` | OCR engine (Tesseract over stdin), line classification, plate-shape finder, tracks, `LiveContext`, `ContextPlan`/`PlannedContext` | Findings carry no text (doc 16) |
| `review.py` | Markers, cards, escalate-only actions, export gate, overrides | No UI (doc 17) |
| `bench/` | Synthetic hard-case clips, simulated detector, coverage/leak metrics, runner | See doc 11 |
| `adapters/` | MediaPipe and YuNet behind the `Detector` protocol | Model files not bundled |

## Key mechanisms
**Lookahead buffer.** Output is delayed `lookahead` frames (default 4). This enables backfilling a
newly detected track into not-yet-emitted frames, and lets the verifier inspect the rendered frame
before release. Limit: frames already emitted cannot be fixed (see KNOWN_LIMITATIONS).

**Ghost tracks.** When a detection disappears the track predicts its box forward (velocity) and
grows it 3% per frame for up to 30 frames, escalated to MOSAIC. This covers detector dropouts.

**Head-region expansion.** Face boxes are expanded 40% per side to cover hairline, ears, and jaw.

**Verifier.** Re-runs a detector on the rendered output. Residual hit -> BLOCK region -> re-scan ->
whole-frame BLOCK if still detected. Verifier exceptions block the frame. The verifier should be a
different model family from the primary detector.

## Face-change path (built in run 003 with a stub replacer; see docs 12 and 13)
track -> identity (coarse bins) -> smoothed head box -> replacer -> patch EMA -> recognizer verification -> policy gates -> composite or demote.

## Planned architecture (Phase 2+)
- **Identity library:** pre-generated, offline-vetted synthetic identities shipped with the app.
  Assigned at track creation using a per-session random seed plus coarse bins only; persisted for the
  track's lifetime in RAM; never derived from fine facial features of the original.
- **Replacement path:** landmarks + pose -> One-Euro smoothing -> aligned crop -> swap model ->
  full-head mask -> relight/color-match -> blend -> temporal stabilizer.
- **Offline two-pass mode:** pass 1 detection plus bidirectional tracking and tracklet clustering;
  pass 2 rendering. Closes the lookahead gap.
- **Budget governor (live):** per-frame compute budget; overrun demotes the lowest-priority tracks
  to BLUR, never skips them.

## Platform plan
Core library (Python now; C++/Rust + ONNX Runtime for shipping) with platform shells. First target:
Apple Silicon Mac (SwiftUI + CoreML/Metal), then iPhone. See `OPEN_DECISIONS.md`.

## Data handling
RAM-only raw frames. Intermediate files hold redacted frames only and live in a temp directory that
is deleted on exit. No network imports exist in the package. Embeddings (Phase 2) are RAM-only and
zeroed at session end.
