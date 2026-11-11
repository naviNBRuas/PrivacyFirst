# ADR 0007: Identity assignment sees only coarse bins
**Status:** accepted (run 003). **Context:** Choosing a synthetic identity by resemblance to the original would
leak identity into the output (and make the mapping reversible). **Decision:** `IdentityAssigner.assign(track_id,
tone_bin, age_bin)` takes no pixels or embeddings (enforced by a test on the signature); randomness comes from a
per-session seed; one identity per track; no collisions among live tracks; unvetted identities refused by default.
**Consequences:** Less natural skin-tone/age matching than a similarity search would give; stronger privacy
properties and simpler vetting. Bins are crude (luma-based) and need fairness testing.
