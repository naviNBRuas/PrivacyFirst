# 17. Review-flow data model (run 006)

The data and rules behind steps 5-6 of `06-ux-flow.md` (pre-publish review and export). No UI: a front end drives a
`ReviewSession` (`review.py`) and gets the rules for free. Built from a finished run with `build_session(pipeline, report.data)`;
the CLI writes it with `--review-json`.

## Objects
- **Marker**: a coalesced segment of risk, `kind` in low_confidence, ghost_track, verifier_escalation, scene_block, context_identifier
  (redacted), context_flagged (left visible), context_scan_error. Fields: id, start/end frame, subject (face track, context region or
  frame), strongest treatment applied, `exposed`, `viewed`, `decision`. Per-frame pipeline events merge when at most 5 frames apart, so a
  flickering detector gives one marker, not hundreds.
- **PersonCard**, **ContextCard**: per-subject summary and the reviewer's escalation `floor`.
- **Overrides**: escalations as `{track: Treatment}` and `{context id: Treatment}`; `to_pipeline_kwargs()` feeds a re-render.
- **ExportDecision**: `allowed`, `hard_blocks`, `unviewed_markers`, `undecided_markers`, `acks_missing`.

## Rules (all unit-tested)
1. Every marker must be **viewed**. A marker with `exposed` (content left visible) must also be **decided**: `accepted` or `escalated`.
2. Reviewers can only **escalate** (blur < mosaic < block), and only to something stronger than what is applied. `relax_person` raises
   `GuardianGateRequired` for a minor-risk person (the gate is not built) and `RelaxationNotSupported` otherwise; `dismiss_context`
   always raises (D13). The pipeline also refuses SWAP as an escalation.
3. Export gate: metadata failure = **hard block**. Failed verification = hard block if any minor-risk person is present, otherwise needs
   the acknowledgement `verification_failed_frames_blocked`. `verification_not_run` and `placeholder_components` need acknowledgements.
4. After a re-render, floors carry over (`build_session(..., carry=overrides)`) but viewed/decided state resets: the pixels changed.
5. Serialisation (`review_version` 1) holds frame numbers, ids, enums and counts only: no pixels, text or paths. The action log records
   what was done, never who.

## Interpretations I made (please confirm or overrule; D13)
- "Blocked or requires acknowledgement (never for minor tracks)" is implemented as above; the pipeline does not yet map failed verifier
  frames to specific tracks, so any minor-risk person in the file triggers the hard block.
- Un-redacting a false positive is not offered, because design rule 2 is escalate-only. The cost is that a false plate-like redaction can
  only be removed by re-running with different settings.
- `not_run` verification and placeholder components are acknowledgeable rather than blocking, since the CLI offers `--no-verify`.

## Not built
Any UI; the guardian gate; segment playback ("viewed" is whatever the front end decides it means); mapping verifier failures to tracks;
carrying decisions across re-renders.
