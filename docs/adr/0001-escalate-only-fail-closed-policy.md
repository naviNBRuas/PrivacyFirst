# ADR 0001: Escalate-only, fail-closed policy
**Status:** accepted. **Context:** Every uncertainty (low confidence, dropout, error) is a leak risk.
**Decision:** Treatments are ordered blur < mosaic < block; every rule may only raise strength
(`types.stronger`). Errors in detector or verifier block the frame. **Consequences:** More
over-redaction and false positives; accepted. Policy is deterministic and testable (no ML inside it).
