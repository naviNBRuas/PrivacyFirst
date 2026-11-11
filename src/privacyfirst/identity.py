"""Synthetic identity library and per-track assignment.

Design rules (ADR 0006):
- Identities come from a pre-generated, vetted LIBRARY, never generated at runtime on the user's device.
- Assignment sees COARSE bins only (tone bin, age bin). `IdentityAssigner.assign` deliberately has no
  image/crop/embedding parameter, so an identity cannot be chosen by resemblance to the original face.
- One identity per tracked person, persistent for the track's life; no two simultaneously active tracks
  share an identity (collision rule).
- Unvetted identities are refused unless explicitly allowed (stub/demo only).
"""
from __future__ import annotations
import json
import random
import secrets
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import numpy as np
from .types import Box

SCHEMA_VERSION = 1
TONE_BINS = (0, 1, 2)            # 0 light, 1 medium, 2 deep (coarse, luma-based)
AGE_BINS = ("adult", "child")    # apparent age of the SYNTHETIC face


@dataclass(frozen=True)
class Identity:
    id: str
    tone_bin: int
    age_bin: str
    child_ok: bool               # approved for minor-risk / unknown-age tracks (stricter vetting)
    vetted: bool                 # passed offline vetting (non-resemblance to real people, licensing)
    source: str                  # "stub" or "generated:<tool>@<version>"
    appearance: dict             # stub renderer parameters; real backends reference an identity vector file


def tone_bin_of(frame: np.ndarray, box: Box) -> int:
    """Crude luma-based tone bin from the central half of the face box. Coarse on purpose."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box.clamp_int(w, h)
    cw, ch = x2 - x1, y2 - y1
    if cw < 4 or ch < 4:
        return 1
    roi = frame[y1 + ch // 4:y2 - ch // 4, x1 + cw // 4:x2 - cw // 4]
    if roi.size == 0:
        return 1
    luma = float(roi.mean())
    return 0 if luma > 170 else (1 if luma > 120 else 2)


class IdentityLibrary:
    def __init__(self, identities):
        self.identities: list[Identity] = list(identities)
        issues = self.validate()
        if issues:
            raise ValueError("invalid identity library: " + "; ".join(issues))

    def validate(self) -> list[str]:
        issues, seen = [], set()
        for i in self.identities:
            if i.id in seen:
                issues.append(f"duplicate id {i.id}")
            seen.add(i.id)
            if i.tone_bin not in TONE_BINS:
                issues.append(f"{i.id}: bad tone_bin {i.tone_bin}")
            if i.age_bin not in AGE_BINS:
                issues.append(f"{i.id}: bad age_bin {i.age_bin}")
            if i.age_bin == "child" and not i.child_ok:
                issues.append(f"{i.id}: child-looking identity must be child_ok (stricter vetting)")
        return issues

    def coverage(self) -> dict:
        return dict(Counter((i.tone_bin, i.age_bin) for i in self.identities))

    @property
    def all_vetted(self) -> bool:
        return all(i.vetted for i in self.identities)

    def to_json(self) -> str:
        return json.dumps({"schema_version": SCHEMA_VERSION, "identities": [asdict(i) for i in self.identities]}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "IdentityLibrary":
        d = json.loads(text)
        if d.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported identity library schema {d.get('schema_version')}")
        return cls(Identity(**x) for x in d["identities"])

    def save(self, path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path) -> "IdentityLibrary":
        return cls.from_json(Path(path).read_text())


def generate_stub_library(seed: int = 0, per_cell: int = 4) -> IdentityLibrary:
    """Deterministic cartoon identities for tests/demos. NOT vetted, NOT photoreal, NOT AI."""
    rng = random.Random(seed)
    skins = {0: (205, 220, 245), 1: (135, 170, 215), 2: (75, 100, 145)}
    hairs = [(30, 40, 60), (20, 20, 20), (60, 90, 150), (150, 150, 160), (40, 70, 110)]
    eyes = [(60, 40, 20), (90, 110, 40), (120, 90, 30), (30, 30, 30)]
    lips = [(80, 70, 170), (90, 90, 190), (70, 60, 140)]
    out = []
    for tone in TONE_BINS:
        for age in AGE_BINS:
            for k in range(per_cell):
                j = lambda c: int(min(255, max(0, c + rng.randint(-12, 12))))
                out.append(Identity(
                    id=f"stub-t{tone}-{age[0]}{k}", tone_bin=tone, age_bin=age,
                    child_ok=(age == "child") or (k % 2 == 0), vetted=False, source="stub",
                    appearance={"skin": [j(c) for c in skins[tone]], "hair": list(rng.choice(hairs)),
                                "eye": list(rng.choice(eyes)), "lip": list(rng.choice(lips)),
                                "hair_style": rng.randint(0, 2)}))
    return IdentityLibrary(out)


class IdentityAssigner:
    def __init__(self, library: IdentityLibrary, seed: Optional[int] = None, allow_unvetted: bool = False):
        self.library = library
        self.allow_unvetted = allow_unvetted
        self._rng = random.Random(secrets.randbits(64) if seed is None else seed)   # per-session random seed
        self.by_track: dict[int, Identity] = {}
        self._in_use: dict[str, int] = {}
        self.assignments = 0

    @property
    def uses_unvetted(self) -> bool:
        return self.allow_unvetted and not self.library.all_vetted

    def _pool(self, age_bin: str) -> list[Identity]:
        lib = [i for i in self.library.identities if self.allow_unvetted or i.vetted]
        if age_bin == "child":
            return [i for i in lib if i.age_bin == "child" and i.child_ok]
        if age_bin == "adult":
            return [i for i in lib if i.age_bin == "adult"]
        return [i for i in lib if i.age_bin == "adult" and i.child_ok]        # unknown age: conservative pool

    def assign(self, track_id: int, tone_bin: int, age_bin: str) -> Optional[Identity]:
        if track_id in self.by_track:
            return self.by_track[track_id]
        pool = self._pool(age_bin)
        for tol in (0, 1, 2):                                                 # widen tone match only if needed
            cands = [i for i in pool if abs(i.tone_bin - tone_bin) <= tol and i.id not in self._in_use]
            if cands:
                pick = self._rng.choice(sorted(cands, key=lambda i: i.id))
                self.by_track[track_id] = pick
                self._in_use[pick.id] = track_id
                self.assignments += 1
                return pick
        return None                                                           # exhausted: caller must demote

    def release(self, track_id: int) -> None:
        ident = self.by_track.pop(track_id, None)
        if ident:
            self._in_use.pop(ident.id, None)
