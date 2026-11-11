# ADR 0005: Independent verifier; keys-only reports
**Status:** accepted. **Decision:** Verification must use a model family different from the primary
detector; a same-model or scripted verifier is flagged in the report as not meaningful. Reports
hold counts and metadata key names only. **Consequences:** Honest "passed" semantics; reports are
safe to share.
