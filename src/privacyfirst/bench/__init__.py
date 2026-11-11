"""Phase 0 benchmark harness: synthetic hard-case clips with ground truth, a failure-mode
detector simulator, leak/coverage metrics, and a detector evaluator for real models.

IMPORTANT: results from `SimulatedDetector` measure how the PIPELINE (ghost tracks, lookahead,
policy) behaves under assumed detector failure patterns. They say nothing about how any real
detector performs. Real-model recall/latency come from `evaluate_detector` on real footage.
"""
