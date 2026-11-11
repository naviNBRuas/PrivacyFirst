# ADR 0008: Two-pass is the default for recorded files; the live tracker keeps explicit hull coverage

Status: accepted (run 004). Builds on ADR 0002.

Context: live lookahead cannot cover a face detected later than the buffer; fragmented IDs would split one person across
synthetic identities. A tracker upgrade that only improved association raised leak, because the old tracker's duplicate
ghosts had been providing unintended coverage.

Decision:
1. `privacyfirst video` defaults to two-pass; `--mode live` remains and its reports carry a warning.
2. Pass 1 keeps geometry only; pass 2 must prove it reads the same file (fingerprints) or abort with no output.
3. Coverage that used to be accidental is explicit: a ghost covers the hull of "stayed" and "kept moving".
4. Hindsight may widen coverage (back-extension, two-sided gaps, whole-person age evidence). It may also unlock a swap
   earlier (confirmed track) or across a short bracketed gap, but never weakens a gate: demotion still only escalates.
5. Tracker changes must pass an A/B on leak AND area, not on ID stability alone.

Consequences: higher redacted area in some scenes; a known residual leak when a blind period exceeds `back_extend`;
the live path still has the lookahead limit.
