"""Recognizer-ensemble verification of a replacement, and per-track swap state."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol
import numpy as np
from .identity import Identity
from .stabilize import OneEuro, PatchStabilizer


class Recognizer(Protocol):
    name: str
    def similarity(self, original: np.ndarray, candidate: np.ndarray) -> float: ...


class FunctionRecognizer:
    """Wraps a callable as a Recognizer (tests, demos, and adapters for real embedding models)."""
    def __init__(self, name: str, fn: Callable[[np.ndarray, np.ndarray], float]):
        self.name, self._fn = name, fn

    def similarity(self, original, candidate) -> float:
        return float(self._fn(original, candidate))


@dataclass
class VerifyResult:
    ok: bool
    similarities: dict
    reason: str = ""


class SwapVerifier:
    """Passes only if EVERY recognizer's similarity is below its threshold. Fails closed on any error.

    The original crop and candidate embeddings exist only in RAM for the duration of this call.
    Minor-risk tracks use the stricter threshold. Needs >= min_recognizers independent families.
    """
    def __init__(self, recognizers: list, max_sim_adult: float = 0.35, max_sim_minor: float = 0.20,
                 min_recognizers: int = 2):
        self.recognizers = list(recognizers)
        self.max_sim_adult, self.max_sim_minor, self.min_recognizers = max_sim_adult, max_sim_minor, min_recognizers

    @property
    def names(self) -> list[str]:
        return [r.name for r in self.recognizers]

    def check(self, original: np.ndarray, candidate: np.ndarray, strict: bool) -> VerifyResult:
        if len(self.recognizers) < self.min_recognizers:
            return VerifyResult(False, {}, "ensemble_too_small")
        limit = self.max_sim_minor if strict else self.max_sim_adult
        sims: dict = {}
        try:
            for r in self.recognizers:
                sims[r.name] = float(r.similarity(original, candidate))
        except Exception:
            return VerifyResult(False, sims, "recognizer_error")
        bad = [n for n, s in sims.items() if not (s < limit)]
        return VerifyResult(not bad, sims, "" if not bad else f"similarity_above_threshold:{','.join(bad)}")


@dataclass
class SwapState:
    identity: Optional[Identity] = None
    identity_tried: bool = False
    verified: Optional[bool] = None
    last_verified: int = -10**9
    demoted_until: int = -1
    dropout_until: int = -1          # demotion caused only by a detection dropout; can be released early
    perm_demoted: bool = False
    demotions: Counter = field(default_factory=Counter)
    stab: PatchStabilizer = field(default_factory=PatchStabilizer)
    filters: tuple = field(default_factory=lambda: tuple(OneEuro(min_cutoff=1.5, beta=0.08) for _ in range(4)))

    def is_demoted(self, idx: int) -> bool:
        return self.perm_demoted or idx < self.demoted_until or idx < self.dropout_until
