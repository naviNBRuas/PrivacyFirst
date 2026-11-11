# 00. Vision and Scope

## Problem
People record and share video that includes bystanders and children who never consented. Existing
tools blur faces manually, miss frames, ignore metadata, and give no evidence of what was protected.

## Vision
A local-first app that, by default, makes faces in video unrecognizable and tells the user honestly
how well it worked: **fail closed, minors first, verify, and be honest about residual risk.**

## Principles
- **Privacy by construction:** no upload path, so "your video never leaves your device" is enforced by absence.
- **Fail closed:** uncertainty increases redaction.
- **Minors by default:** strongest transform; exceptions require friction and are recorded.
- **Verifiable:** every export ships with a privacy report, and verification is independent of the privacyfirst.
- **Honest:** reduces risk; does not guarantee legal anonymization.
- **Not a deepfake tool:** no user-chosen target identities, ever.

## In scope (MVP)
Face detection and tracking, redaction with automatic fallbacks, stable per-person synthetic identity
(Phase 2), metadata stripping, privacy report, pre-publish review, minors defaults.

## Out of scope (MVP)
Cloud processing, accounts, social sharing, real-time streaming to third parties, legal
certification, user-supplied replacement faces, training on user data.

## Personas
- **Parent/guardian** sharing clips that include other people's children.
- **Educator/organizer** publishing event footage.
- **Journalist/activist** protecting bystanders and sources.

## Success criteria
| Metric | Target |
|---|---|
| Frames output with a detectable unredacted face (benchmark) | 0 |
| Verification pass rate on benchmark | tracked per release, regressions block release |
| Metadata leaks after export | 0 |
| Users completing the review step | >90% |
| Live latency (Phase 3) | <=150 ms added |
