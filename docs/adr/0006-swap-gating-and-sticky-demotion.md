# ADR 0006: Swap is gated, never default, with sticky demotion
**Status:** accepted (run 003). **Context:** A changed face that looks real is exactly what makes a failure
dangerous: a bad swap looks like a good one. **Decision:** `swap_enabled` is off by default; SWAP requires every gate
(confidence, track stability, replacer health, identity availability, no active demotion, recognizer pass, budget).
Minor-risk and unknown-age people need an explicit ensemble PASS. Demotion is sticky (30 frames) and verification
failure is permanent for the track; late failures also demote frames still buffered. **Consequences:** More
mosaic time than a naive design (measured: ~44% swap share in the baseline simulated scenario); less flicker and a
fail-closed default. Thresholds need calibration on real models.
