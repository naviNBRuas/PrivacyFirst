"""PrivacyFirst: local-first, fail-closed face redaction.

Phase 1 core: detection interface, tracking with ghost tracks, a deterministic
policy engine, blur/mosaic/block fallbacks, lookahead buffering with backfill,
metadata stripping, residual-face verification, and a privacy report.

Photoreal face replacement (Phase 2) is NOT implemented yet. Treatment.SWAP is
reserved and the policy engine will never emit it in Phase 1.
"""
__version__ = "0.6.0"
