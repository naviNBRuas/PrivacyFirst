# 05. Safety Controls

| Control | Description | Where enforced |
|---|---|---|
| Fail-closed hierarchy | blur -> mosaic -> block; escalate-only | `types.stronger`, `policy.py`, `fallback.py` |
| Detector failure | Any exception blocks the whole frame | `pipeline.push` |
| Dark/unreliable scene | "No faces found" is not trusted below a luma threshold | `policy.scene_decision` |
| Ghost tracks | Keep redacting predicted region after a dropout | `tracking.py` |
| Backfill | Cover already-buffered frames when a face is first detected | `pipeline._backfill` |
| Verifier | Independent re-scan of rendered output; escalate or block | `pipeline._verify` |
| Minors default | Unknown age = minor = at least mosaic | `policy.is_minor_risk` |
| Minor exceptions (Phase 2) | Guardian gate (device passcode/biometric + confirmation); logged; never blocks reporting | UX + report |
| Audio default | Dropped unless explicitly kept; kept audio is flagged "voice not anonymized" | `metadata.strip_video`, report |
| Metadata | Stripped and re-verified; export blocked/flagged if verification fails | `metadata.py`, CLI exit code |
| No network | No network-capable imports; enforced by test | `tests/test_no_network.py` |
| No training on user data | No upload path exists; any future opt-in is separate, granular, revocable, excludes minors by default | Architecture |
| Honest claims | Residual-risk statement in every report and export screen | `report.py` |
| Swap gating | SWAP off by default; every gate must pass; minors need an explicit ensemble PASS; sticky demotion; late failures demote buffered frames | `policy.py`, `pipeline.py` (doc 13) |
| Identity assignment by coarse bins only | No pixels/embeddings reach assignment; no collisions; unvetted identities refused | `identity.py`, signature test |
| Context identifiers | OCR + rules block plate/contact/address text; other text flagged; scan failure blocks the frame; findings never hold text | `context.py`, `pipeline._ingest_context` (doc 16) |
| Review gate | Escalate-only reviewer actions; every marker viewed, exposed ones decided; metadata failure hard-blocks export | `review.py` (doc 17) |
| Anti-misuse | No user-chosen target faces; provenance marking for synthetic content (Phase 2) | Design rule |

## Release gates
1. Zero known leak frames on the benchmark set.
2. Metadata verification passes on the metadata test corpus.
3. Verifier from a different family than the primary detector.
4. Independent red-team pass (recognition APIs, human reviewers, adversarial footage).
5. Legal review of all product copy that mentions anonymization.

## Incident handling
Any confirmed leak -> release-blocking bug, regression test added to the corpus before the fix ships,
report schema bumped if the report failed to flag it.
