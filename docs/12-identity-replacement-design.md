# 12. Identity Replacement Design (the AI face change)

**Product intent (from the founder):** redaction is done by *changing facial features with AI*. A natural face
is still visible, it is not blurred or blocked, but it is a different, synthetic person. Blur/mosaic/block exist
only as the fail-closed safety net.

**Status (run 003):** the gates, identity library/assignment, stabilizers, blending, recognizer-verification wiring and a
non-AI stub replacer are built and tested (see `docs/13`). **No real swap model is integrated yet**, and no real
recognizers; those need model weights (Phase 0 / run 005).

## 1. What changes and what is preserved
| Changed (identity-bearing) | Preserved (so it looks like the same moment) |
|---|---|
| Facial structure, eye shape/color, nose, mouth/lips, brows | Head pose (yaw/pitch/roll) |
| Jaw, cheeks, ears, hairline, hair outline | Expression (smile, speech, blinks) |
| Skin texture, moles, marks | Gaze direction |
| (optional) facial hair, glasses | Scene lighting and color temperature |
| | Coarse skin-tone compatibility, apparent age bucket, head position/scale |

Because identity leaks through the *whole head*, the replaced region is the full head (face, jaw, ears,
hairline), not only the inner face rectangle.

## 2. Technique options
| Approach | How | Real-time on device | Identity-change strength | Notes |
|---|---|---|---|---|
| **A. Encoder-based identity swap** (SimSwap / FaceDancer / GHOST class) | Encode target pose/expression/lighting; inject a *synthetic identity vector*; decode a face; blend | Feasible at 128-256 px on NPU/GPU | Medium-high, must be verified | **Recommended for live and the MVP** |
| B. Diffusion-based identity editing | Condition a diffusion model on pose/expression and a new identity | No (seconds per frame) | High | Offline "high quality" export mode later |
| C. 3DMM / neural re-render | Fit a 3D face model, swap shape/texture parameters, render | Possible, complex | High on structure, lower realism | Good for pose/expression fidelity; larger engineering cost |
| D. GAN latent editing of the real face | Move the real face's latent away along identity directions | Partly | Unreliable: easy to leave residual identity | Not recommended as the primary method |

**Decision for MVP:** approach A, using a vetted library of synthetic identities, then B as an optional offline mode.

## 3. Pipeline (per tracked person, per frame)
```
track box + landmarks + pose  ->  One-Euro smoothing  ->  aligned crop (128-256 px)
  -> swap model(crop, identity_vector[track])  ->  face patch
  -> head mask (segmentation: face+hair+ears+neck seam)
  -> color match + relight + grain match  ->  feathered blend into frame
  -> temporal stabilizer  ->  verification sampler  ->  output
```
Backend contract (to be added in the next run):
```python
class FaceReplacer(Protocol):
    name: str
    def prepare(self, identity: Identity) -> None: ...            # cache identity vector once per track
    def replace(self, frame, track, landmarks) -> Replacement: ...  # patch + head mask + health score
```
A **stub backend** (non-AI, deterministic) will ship with the tests so every gate around the model is testable
without weights.

## 4. Stable synthetic identity (one per person, whole video)
- **Library, not runtime generation:** an offline-generated set of identities (portrait + embedding), vetted for
  non-resemblance to real people and balanced across skin tone, apparent age, and gender presentation.
- **Assignment:** at track creation, choose using a **per-session random seed** and **coarse bins only**
  (skin-tone bucket, apparent-age bucket, face size). Never from fine facial similarity to the original.
- **Persistence:** track ID -> identity, in RAM, for the video's life; cleared at export.
- **Re-appearance:** offline mode clusters tracklets (ephemeral appearance embeddings) so a person who leaves
  and returns keeps the same synthetic identity. Live mode may issue a new identity after a long absence and
  must say so. The benchmark shows current track-ID instability (motion blur, crowds), so tracker upgrades
  come before this.
- **Collision rule:** two tracks in one frame never share an identity.

## 5. Temporal stability (no flicker)
Identity vector fixed per track; smoothed landmarks and pose; patch-level EMA or flow-guided warping between
frames; scene-cut detection resets filters; hysteresis on mask edges; flicker metric tracked in CI.

## 6. Blending and realism
Head segmentation (hair/ears/neck seam), color transfer in a perceptual space, relighting from estimated
illumination, grain/noise and compression matching, feathered alpha, edge handling for glasses, hands over the
face, and extreme angles (fail to mosaic rather than show a broken swap).

## 7. Verification gates: when a swap is allowed to stay
A track shows SWAP on a frame only if **all** hold; otherwise the existing policy escalates (mosaic/block):
1. Detection confidence >= threshold and track stable for >= N frames.
2. Replacer health score OK (pose within trained range, mask quality, no occlusion failure).
3. Compute budget OK (live).
4. **Recognizer-ensemble check (sampled, and on every anomaly):** embeddings (RAM-only) of the original crop vs
   the output crop from >= 2 independent recognizer families must be below calibrated similarity thresholds.
5. Synthetic output must not match library neighbors of real people beyond a threshold (best-effort vetting).
6. Not a minor, **or** the stricter minor-gate below passes.

**Demotion is sticky** for a segment (hysteresis) so the video does not flip between a face and mosaic every few
frames. The review screen lists every demoted segment.

## 8. Children
The founder's direction is that the AI face change applies to everyone. The safeguard is a **stricter gate, not a
ban:** minors (and unknown age) get the photoreal change only if the stricter recognizer thresholds pass, the
identity comes from a children-appropriate vetted library, and the guardian gate is not bypassed; otherwise the
person falls back to mosaic. Rationale: age estimation is weakest near 18, verification is hardest for child
faces, and photoreal synthetic child faces carry training-data and misuse risk. See ADR 0004.

## 9. Performance budget (targets, to be measured in Phase 0)
Per face, 256 px: swap <= 12 ms, mask <= 3 ms, blend <= 2 ms on Apple Neural Engine class hardware; up to 3
faces at 24 fps (live). Beyond budget: demote lowest-priority tracks to blur, never skip them.

## 10. Risks
Residual identity leakage; uncanny/temporal artifacts; uneven quality across skin tones and ages (fairness
testing required); glasses, masks, hands; model licenses (e.g. some popular swap models are non-commercial);
misuse as a deepfake tool (no user-chosen targets, provenance marking); false confidence from a passing check.

## 11. Implementation steps (runs 003+)
1. `Treatment.SWAP` made real in policy with the gates above; `FaceReplacer` protocol; stub backend.
2. Identity library schema, loader, vetting script, assignment with collision rule and tests.
3. Head mask + blending module with synthetic tests (seam error, color shift metrics).
4. Temporal stabilizer + flicker metric.
5. Recognizer-ensemble verifier wiring, threshold calibration harness.
6. Plug a real swap model (needs weights: see MODEL_SETUP) and run Phase 0 quality/leak benchmark on consented data.
7. Review UI data model for demoted segments.

## 12. Acceptance criteria
Zero leak frames on benchmark; recognizer match-rate below calibrated thresholds on every ensemble member; flicker
metric under threshold; same identity per person across the clip; fallback demotion rate reported; no change in
fail-closed guarantees from Phase 1.
