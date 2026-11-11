# 06. UX Flow

## Principles
Safe by default; show risk, not just output; make the careful path the easy path; never imply certainty.

## Flow
1. **Onboarding.** Everything stays on this device. What the tool does and does not do. Minors
   policy. Residual-risk statement (same wording as the report).
2. **Choose input.** Import a video/photo, or record (live mode, Phase 3).
3. **Choose preset.** *Strict* (default; children may be present), *Standard* (known adults only),
   *Custom*. Standard shows a one-line warning about what it relaxes.
4. **Processing.** Progress, live preview of the **redacted** output only. The raw frame is never displayed
   in live mode.
5. **Pre-publish review (required).**
   - Timeline with risk markers: low-confidence, ghost-track, verifier escalation, scene block,
     context identifier.
   - Per-person cards: treatment applied, minor-risk badge, option to escalate (never to relax a
     minor without the guardian gate).
   - Checklist of what is NOT covered: voice, context identifiers, body, background (until those phases ship).
   - Every flagged segment must be viewed before Export is enabled.
6. **Export.** Metadata removal confirmed; audio state shown; choose resolution. If verification
   failed or metadata verification failed, Export is blocked or requires explicit acknowledgement
   (never for minor tracks).
7. **Privacy report.** One page, shareable if the user chooses: counts, treatments, fallbacks,
   verification status, metadata keys removed, warnings, residual-risk statement. No images.

## Data model
The review state and the export gate described above are implemented as data in `review.py` (doc 17); the UI is not built.

## Copy rules
- Say "reduces risk", never "anonymous" or "safe".
- Verification states use fixed wording: *passed*, *passed after escalation*, *failed (frames blocked)*, *not run*.
- Placeholder components are surfaced as warnings in the UI, not hidden in docs.

## Guardian gate (honest framing)
Single-device parental controls are friction, not authentication. The UI says so, uses the OS
passcode/biometric, and records that an exception was used (not who).

## Accessibility
Review markers are keyboard-navigable and have text labels; no color-only status.
