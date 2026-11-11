# ADR 0009: Context scan redacts identifier-like text and only flags the rest

**Status:** accepted for v0 (run 006); decision D11 stays open.
**Decision:** plate-, contact- and address-like text is blocked automatically. Other readable text and unread plate-shaped objects are
*flagged* as review markers that require a decision, and are not redacted unless the reviewer escalates them.
**Why:** redacting all readable text would erase signs, labels and clothing text in most footage and teach people to disable the scan.
The review step exists for uncertain cases. **Cost:** until a decision is made, ordinary text can still carry location or school cues.
**Alternative (D11):** `text_treatment = Treatment.MOSAIC` redacts everything readable (strongest, most destructive).
**Related rule:** recognised text is never stored in findings, reports or review files (no hash either).
