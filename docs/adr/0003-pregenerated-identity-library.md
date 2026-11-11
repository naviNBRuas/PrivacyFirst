# ADR 0003: Pre-generated, vetted synthetic identity library
**Status:** proposed (Phase 2). **Context:** Runtime generation on-device is costly, unvetted, and
license-sensitive. **Decision:** Ship an offline-generated library of synthetic identities, vetted
against real-person resemblance, balanced across skin tone/age/gender. Assign per track using a
per-session random seed plus coarse bins; never from fine facial features of the original.
**Consequences:** Bounded diversity; easier verification and licensing review.
