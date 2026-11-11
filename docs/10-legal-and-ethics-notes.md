# 10. Legal and Ethics Notes

> Engineering notes, **not legal advice.** Have qualified counsel review product copy and data flows
> for each target jurisdiction before launch.

## Positioning
Redaction and face replacement **reduce** privacy risk. They do not, by themselves, establish legal
anonymization or de-identification under GDPR/UK GDPR, LGPD, CCPA/CPRA, COPPA, BIPA, or similar
regimes. Whether data is "anonymous" depends on the means reasonably likely to be used to re-identify
a person, including non-face cues and external information.

## Areas to review
- **Biometric data:** running face detection or recognition models may itself be regulated, even
  on-device; verification models compute embeddings (RAM-only, never stored or sent).
- **Children's data:** age estimation is a biometric inference; parental consent regimes vary; avoid
  collecting anything about minors; keep exceptions local and minimal.
- **Synthetic faces:** generating realistic faces of apparent minors raises ethical and legal risk
  (training data, misuse). Hence non-photoreal defaults for minors.
- **Model licenses and training data:** non-commercial licenses, contested datasets (see doc 03).
- **Consent for beta/benchmarks:** only consented or synthetic footage; ethics review for any child imagery.
- **Marketing claims:** no "anonymous", "GDPR-compliant", or "untraceable" wording without legal sign-off.

## Misuse and ethics
- No user-chosen target identities; provenance marking of synthetic content; acceptable-use policy.
- Local-only design means the vendor cannot moderate content. Accept and document that trade-off.
- Do not market for evading lawful investigation or concealing wrongdoing.

## Data policy (engineering commitments)
No upload code; no telemetry containing media/biometrics; no training on user data without explicit,
granular, revocable opt-in that excludes minors by default.
