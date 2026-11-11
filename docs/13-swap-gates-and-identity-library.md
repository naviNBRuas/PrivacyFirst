# 13. Swap Gates, Identity Library, and the Replacer Contract

Implements the policy half of `docs/12`. Everything here is testable without model weights because the only
replacer shipped is a **non-AI stub** (flat cartoon face). A real model plugs in behind the same interface.

## 1. When a person is shown as a changed face (SWAP)
`PolicyConfig.swap_enabled` is **off by default**. When on, a track is shown as SWAP on a frame only if every
gate passes; otherwise it is demoted (mosaic, or blur for budget). Reason codes appear as `swap_gate:<reason>`.

| Reason | Fails when | Demotes to | Sticky |
|---|---|---|---|
| `ghost_track` | detection lost (predicted box only) | mosaic | yes |
| `low_confidence` | detection confidence < 0.70 | mosaic | yes |
| `track_not_stable` | fewer than 5 matched frames | mosaic | no |
| `no_identity` | identity pool exhausted or empty | mosaic | no |
| `sticky_demotion` | a recent sticky demotion is still active | mosaic | (does not extend) |
| `replacer_error` | replacer raised | mosaic | yes |
| `replacer_unhealthy` | replacer health < 0.60, or never evaluated | mosaic | yes |
| `verification_failed` | recognizer ensemble found a match | mosaic, **permanent for the track** | yes |
| `minor_gate_not_passed` | minor-risk/unknown-age person without an explicit verifier PASS, a `child_ok` identity, and the minor path enabled | mosaic | no |
| `over_budget` | more swaps than `max_swaps` this frame (smallest faces lose) | **blur** | no |

**Hysteresis:** a sticky demotion lasts `swap_sticky_frames` (30) so the output does not flip between a face and a
mosaic every few frames. **Late failures:** if verification fails while earlier frames are still in the lookahead
buffer, those frames are demoted too at render time. **Never on faith:** "not checked" is not a pass; minors and
unknown-age people need an explicit PASS from at least two independent recognizers.

## 2. Identity library
JSON, `schema_version` 1 (`IdentityLibrary.to_json/from_json`). Each identity: `id`, `tone_bin` (0 light, 1 medium,
2 deep), `age_bin` (apparent age of the synthetic face: adult/child), `child_ok` (stricter vetting for minor-risk
use), `vetted`, `source`, `appearance` (stub parameters; a real backend references an identity-vector file).
Validation: unique ids, valid bins, child-looking identities must be `child_ok`.

**Assignment** (`IdentityAssigner`): per-session random seed; sees **only** `track_id, tone_bin, age_bin` (a test pins
the signature, so no crop or embedding can reach it); persistent per track; no two live tracks share an identity;
unknown age draws from adult-looking, `child_ok` identities (never a child-looking face on an unknown-age person);
unvetted identities are refused unless explicitly allowed (stub/demo); tone matching widens only if the pool is empty;
exhaustion returns `None` and the person is demoted. Identities are released when a track ends.

## 3. Temporal stability and blending
One-Euro filter on box geometry (per track), EMA on aligned patches, a flicker metric (mean frame-to-frame change of
aligned patches). Blending: soft elliptical head mask (to be replaced by segmentation), LAB color transfer from the
original region (relighting proxy), grain matching, feathered alpha composite. Outside the head box and outside the
mask support, pixels are unchanged (tested).

## 4. Recognizer-ensemble verification (`SwapVerifier`)
Contract for a `Recognizer`: `similarity(original_crop, candidate_crop) -> float`, higher = more alike (e.g. cosine
similarity of face embeddings). Embeddings exist only in RAM for the call. Passes only if **every** recognizer is
below its threshold (default 0.35 adult, **0.20 minor-risk**, both placeholders until calibrated); fewer than two
recognizers, or any exception, fails closed. Checked on first eligibility and every `verify_every` (5) frames.

## 5. Replacer contract (what a real model must satisfy)
```python
class FaceReplacer(Protocol):
    name: str
    is_stub: bool
    def replace(self, frame, track, head_box, identity, frame_idx) -> Replacement
# Replacement: head_box (frame-clamped ints), patch (HxWx3 aligned to head_box), mask (HxW float 0-1), health (0-1)
```
Requirements: no network access; identity vectors loaded once per track and kept in RAM; `health` must drop for
out-of-range pose, occlusion, bad mask, or low confidence (the policy trusts it); deterministic per (track, frame)
for testability; raise rather than return garbage. `is_stub=True` triggers report warnings.

## 6. Configuration reference (`PolicyConfig`)
`swap_enabled=False`, `swap_min_conf=0.70`, `swap_min_track_hits=5`, `swap_min_health=0.60`,
`swap_demote_treatment=MOSAIC`, `swap_sticky_frames=30`, `minor_swap_allowed=True`. Pipeline: `max_swaps`,
`verify_every`. All thresholds are **uncalibrated placeholders** until Phase 0 real-model data exists.

## 7. Report fields
`tracks[].synthetic_identity_id`, `tracks[].swap_demotions`, and a `swap` section: replacer, stub flag, region-frames
swapped, render-time demotions, demotions by reason, identity assignments, unvetted-library flag, replacer errors,
recognizer names/thresholds/checks/failures. Warnings fire for: stub replacer, unvetted library, no recognizer
verification, replacer errors.
