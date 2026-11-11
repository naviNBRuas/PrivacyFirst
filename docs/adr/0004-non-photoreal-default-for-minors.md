# ADR 0004: Gated photoreal change for minors (revised in run 002)
**Status:** accepted (revises the original "non-photoreal default"). **Context:** The founder wants redaction to
be an AI change of facial features (a natural face remains, not blur) for everyone. Child faces are the hardest to
verify, age estimates are least reliable near 18, and photoreal synthetic child faces carry training-data and
misuse risk. **Decision:** Photoreal identity replacement applies to minors and unknown-age people only when a
**stricter gate** passes (tighter recognizer thresholds, a children-appropriate vetted identity library, guardian
gate intact); otherwise they fall back to mosaic or stronger. Until Phase 2 ships, minors get mosaic.
**Consequences:** The product matches the intended look while keeping the safest outcome when verification is
uncertain. More demotions to mosaic are expected for children; reported in the privacy report and review screen.
