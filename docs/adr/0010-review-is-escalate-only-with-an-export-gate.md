# ADR 0010: Review can only escalate; export is gated

**Status:** accepted for v0 (run 006); interpretations listed in docs/17 and decision D13.
**Decision:** a reviewer may only move treatments up (blur < mosaic < block). Relaxing or dismissing is refused (for minor-risk people the
refusal names the guardian gate, which is not built). Export requires every marker viewed, every exposed marker decided, no hard block
(metadata failure; failed verification with minor-risk people present) and every required acknowledgement.
**Why:** extends ADR 0001 (escalate-only) to the human step: a tired reviewer clicking through must not be able to weaken protection.
**Cost:** a false positive cannot be un-redacted without a re-run.
