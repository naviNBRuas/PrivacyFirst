# Open Decisions

| # | Decision | Options | Needed by | Default if unanswered |
|---|---|---|---|---|
| D1 | First platform | Apple Silicon Mac + iPhone / Windows / Android | Phase 0 | Apple Silicon Mac (SwiftUI + CoreML), core stays portable |
| D2 | Transform for minors | **Decided (run 002): photoreal change behind a stricter verification gate, mosaic fallback** (ADR 0004). Open: exact thresholds | Phase 2 | Gated photoreal; mosaic until Phase 2 |
| D3 | Distribution model (**proceeding on the default until you answer**) | Open source / commercial / both | Phase 0 (gates model choice) | Assume commercial-compatible licenses only |
| D4 | First jurisdictions | e.g. EU/UK, US states, Brazil | Phase 4 | Lawyer review before any "anonymization" wording ships |
| D5 | Product name | **Decided: PrivacyFirst** | n/a | n/a |
| D6 | Provenance marking | C2PA manifest / visible mark / none | Phase 2 | C2PA manifest noting synthetic faces |
| D7 | Verifier ensemble | Which recognizers, thresholds | Phase 0-2 | Two independent families, calibrated per recognizer |
| D8 | Swap gate thresholds and hysteresis | conf 0.70, 5 stable frames, health 0.60, sticky 30 (replacer/recognizer) and **15 (dropout, run 004)**, interp gap 4, **two-pass early release after 3 detections (run 005)**, recognizer 0.35 adult / 0.20 minor | Run 005 (needs real models) | Placeholders; calibrate on real data |
| D10 | Two-pass cost/coverage dial | `back_extend` 16, ghost hull cap 15 (30 buys 0.6 leak points for +4.3 area points) | Phase 2 UX | Current values; say if you prefer more coverage or less hidden area |
| D9 | What viewers see during demotion | Mosaic (current) / blur / stylized mask | Phase 2 UX | Mosaic (strongest, least ambiguous) |
| D11 | Ordinary readable text (signs, labels): redact or only flag? | Flag for review (current, ADR 0009) / redact all readable text (`text_treatment=MOSAIC`) | Before the scan is default-on | Flag; identifiers are blocked |
| D12 | Context scan default and cadence | Off + every 3rd frame (current) / default-on for recorded files / every frame | Phase 4 | Off; every 3rd frame (0.54 s per frame on one core) |
| D13 | Review-model interpretations (docs/17): minor-risk presence hard-blocks a failed verification; no dismiss of redactions; `not_run`/placeholders acknowledgeable | Confirm, or allow dismissal of false positives behind a confirmation | Phase 2 UX | As implemented |
