# 03. Model Selection and Licensing

> Licenses and weight terms change and differ between code and weights. The notes below reflect
> understanding at the time of writing. **Verify each license, and each weight file's training-data
> provenance, before shipping.** Phase 0 exit requires this to be cleared in writing.

## Stage-by-stage candidates
| Stage | Candidates | Notes / risks |
|---|---|---|
| Face detection | MediaPipe BlazeFace / Face Detector, YuNet (OpenCV Zoo) | Permissive. Prefer for shipping. Many top-accuracy face detectors (SCRFD, RetinaFace weights, InsightFace packs) carry non-commercial terms; YOLO-face variants are often AGPL |
| Landmarks / pose / gaze | MediaPipe Face Landmarker (478 pts, blendshapes, iris) | On-device friendly. Gaze needs iris landmarks or a dedicated model |
| Tracking | ByteTrack, OC-SORT, BoT-SORT | Permissive. Re-ID embeddings are biometric: RAM-only |
| Face swap (Phase 2) | SimSwap, FaceDancer, GHOST, BlendSwap-class | `inswapper_128` is non-commercial. Check training data of every candidate |
| Head parsing / matting | BiSeNet-style face parsing, MODNet-class matting | Needed for hair/ears/jaw coverage |
| Synthetic identity generation | Offline generation, then ship a vetted library | StyleGAN weights carry NVIDIA's non-commercial terms. Prefer licensing-clean generators; generate and vet offline, never at runtime on-device |
| Verification | Ensemble of ArcFace/AdaFace/MagFace/EdgeFace-class recognizers | Independent of the swap model; check weight licenses; some are trained on retracted/contested datasets |
| Age bucket | Small CNN on crop | Biometric inference: on-device, ephemeral, calibrated to over-flag; weakest near 18; demographic variance. Never a hard gate to loosen protections |
| Plates / text / tattoos | Lightweight plate detector + on-device OCR | Tattoos/uniforms weakest: warn, don't claim detection |
| Voice | DSP pitch/formant shift (MVP), neural voice conversion later | DSP alone is often reversible; test against speaker-ID models |

## Selection criteria (in order)
1. License clears the intended distribution (commercial or not).
2. Training-data provenance is defensible (no retracted/non-consented datasets where avoidable).
3. Recall on small/profile/occluded faces (primary detector); independence from primary (verifier).
4. Latency on target NPU/GPU within the budget (doc 02).
5. Quantization-friendliness (CoreML/ONNX int8/fp16).

## Phase 0 bake-off protocol
- Test set: consented or fully synthetic footage with ground-truth boxes, including night, motion
  blur, crowds, masks, profile, tiny faces, children (consented only).
- Metrics: recall at fixed FPPI, p95 latency per face on target hardware, memory, verifier
  match-rate after redaction, flicker score for swap candidates.
- Output: a table per stage plus a written license clearance memo.

## What the current code uses
`HaarDetector` (OpenCV cascades) is a **plumbing placeholder only**. Reports flag it, and doc 08
lists tests that must pass before it is replaced.
