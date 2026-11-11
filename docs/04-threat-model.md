# 04. Privacy Threat Model

## Assets
Identity of people in footage (faces first, then voice, body, context); original frames; any
embeddings or crops; metadata (GPS, device, time); the privacy report.

## Adversaries
| # | Adversary | Capability |
|---|---|---|
| A1 | Casual viewer who knows the person | Human recognition, context knowledge |
| A2 | Automated face recognition | Scraping + search engines, strong and improving models |
| A3 | Motivated investigator | Context: location, school, clothing, voice, social graph |
| A4 | Forensic adversary | Tries to reverse blur/mosaic/swap; artifact analysis |
| A5 | Device/app compromise | Malware, backups, sync, crash dumps, logs |
| A6 | Misuser of the tool | Deepfakes, evasion of moderation, impersonation |

## Threats and mitigations
| Threat | Adv. | Mitigation | Status |
|---|---|---|---|
| Missed detection (profile, blur, dark, masks, tiny) | A1-A3 | Low threshold, ghost tracks, backfill, dark-scene block, verifier | Partial |
| Face first seen beyond buffer horizon | A1-A3 | Two-pass offline mode; honest live limits | Planned (see limitations) |
| Residual identity after redaction | A2 | Destructive treatments, verifier escalation | Done / needs real verifier |
| Identity leakage through swapped face | A2 | Full-head mask, recognizer ensemble thresholds, blur on fail | Phase 2 |
| Reversal of weak blur | A4 | Heavy double Gaussian; mosaic/block for risky tracks; never ship blur-only for minors | Done |
| Non-face re-identification (body, clothing, tattoos, voice, background) | A1, A3 | Audio dropped by default; context scan; body/background options; report lists what is NOT covered | Partial |
| Metadata and sidecar leaks | A3, A5 | Strip + ffprobe re-verification; report keys only | Done |
| Raw frames/embeddings persisted | A5 | RAM-only buffers; temp dir holds redacted frames only; no network imports (tested) | Done |
| Report leaks sensitive data | A3, A5 | Counts and key names only | Done |
| Minors misclassified as adult | A1-A3 | Unknown = minor; over-flag threshold; escalate-only | Done |
| Guardian gate bypass | misuse | Honest: friction, not authentication; exceptions logged in report | Phase 2 |
| Synthetic face resembles a real person | A1, A2 | Offline vetting of the identity library; documented as non-exhaustive | Phase 2 |
| Synthetic identity chosen by resemblance to the original | A2 | Assignment sees coarse bins only; random per-session seed; signature test | Done (run 003) |
| Swap looks real but leaks identity | A1, A2 | Recognizer-ensemble gate (stricter for minors); permanent demotion on failure; render-time demotion of buffered frames | Done with stub recognizers; real ones pending |
| Identity flicker / identity changes mid-video | A1 | Persistent per-track identity; One-Euro + patch EMA; measured flicker; track-ID fragmentation still open | Partial |
| Identity pool exhaustion (crowds) | n/a | Exhaustion demotes to mosaic (`no_identity`) | Done |
| Tool misuse for deepfakes | A6 | No user-chosen target faces; provenance mark on exports; acceptable-use policy | Phase 2-4 |
| User over-trust | all | Residual-risk text on every report/export; verifier-status wording | Done |

## Trust boundaries
Device only. There is no server. Any future network feature (updates, telemetry, opt-in
contributions) must be a separate, reviewed module that cannot access frame buffers.

## Out of scope / accepted risks
- Adversaries with the original footage or a prior unredacted copy.
- Physical-world identification unrelated to the video.
- Compromised OS or hardware.
- Legal anonymization status (jurisdiction-specific).

## Review cadence
Re-run this model at each phase gate and whenever a new model or capability is added.
