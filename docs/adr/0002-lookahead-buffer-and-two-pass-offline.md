# ADR 0002: Lookahead buffer now, two-pass offline later
**Status:** accepted. **Context:** Faces detected late leave earlier frames exposed. **Decision:**
Live and streaming use an N-frame lookahead with backfill; recorded video will use a two-pass
bidirectional design (Phase 1b). **Consequences:** Live mode retains an irreducible residual risk
that must be disclosed; recorded mode can close it. A characterization test documents the current gap.
