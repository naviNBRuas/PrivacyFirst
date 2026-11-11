"""Context-identifier scan v0 (run 006): plates, contact details, addresses and other readable text.

Faces are not the only thing that identifies someone. A licence plate, a phone number on a poster, an e-mail on a
laptop or a street address on a letter can identify a person (or a child's home) just as well. This module looks for them
with ordinary OCR plus rules, then hands REGIONS to the pipeline, which destroys them (BLOCK) exactly like a face.

Design rules (same spirit as the face path):
  * Recognised text NEVER leaves this module. A `ContextFinding` holds a kind, a box and a confidence, never the string
    (not even a hash: a plate or phone number has so little entropy that a hash is a lookup table). Reports and the review
    model therefore cannot leak what the OCR read. Raw frames reach the OCR engine through a pipe (stdin), never a file.
  * Only identifier-like text is redacted (plate, contact, address). Ordinary text (a shop sign) and plate-shaped things the
    OCR could not read are FLAGGED for the review step instead (docs/16, decision D11). A flag never changes pixels.
  * A track's treatment only escalates: once any sighting is identifier-like, every frame of that track gets the strong
    treatment, including the frames where the OCR read something weaker or nothing.
  * An OCR failure on a scanned frame blocks that frame (same rule as a detector error). A missing engine is reported
    before any output is produced; there is no silent fallback to "no scan".
  * It is a HEURISTIC. It cannot find text it cannot read (small, blurred, rotated, stylised, non-English, upside down),
    and name tags, uniforms, logos and tattoos are not scanned at all. Reports say so.

Two ways to feed the pipeline, both implementing `frame(idx, frame) -> ContextFrame`:
  * `LiveContext`    scans every `scan_every` frames as they arrive, holds regions between scans, backfills the lookahead.
  * `PlannedContext` replays a `ContextPlan` built by whole-file analysis (`build_context_plan`): gaps between sightings are
                     interpolated from both sides and every track is extended before/after its first/last sighting.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, Sequence
import cv2
import numpy as np
from .types import STRENGTH, Box, Treatment, stronger


class ContextKind(str, Enum):
    PLATE = "plate_like"                 # licence-plate-like token (redacted by default)
    CONTACT = "contact_like"             # e-mail, phone number, URL, @handle (redacted by default)
    ADDRESS = "address_like"             # street address, postal code (redacted by default)
    TEXT = "text"                        # readable text that is not identifier-like (flagged, not redacted by default)
    PLATE_SHAPE = "plate_shape_unread"   # plate-shaped object whose text the OCR could not read (flagged by default)


IDENTIFIER_KINDS = frozenset({ContextKind.PLATE, ContextKind.CONTACT, ContextKind.ADDRESS})
_KIND_RANK = {ContextKind.PLATE: 3, ContextKind.CONTACT: 3, ContextKind.ADDRESS: 3, ContextKind.PLATE_SHAPE: 2, ContextKind.TEXT: 1}


class OcrError(RuntimeError):
    """The OCR engine failed on a frame. The pipeline blocks that frame."""


class OcrUnavailable(RuntimeError):
    """The OCR engine or its language data is not installed. Reported before any output is produced."""


# --------------------------------------------------------------------------------------------- configuration
@dataclass
class ContextConfig:
    scan_every: int = 3                      # run the scan on every Nth frame (cost/coverage dial, decision D12)
    # --- what happens to each kind. None = flag for review only, pixels untouched.
    plate_treatment: Optional[Treatment] = Treatment.BLOCK
    contact_treatment: Optional[Treatment] = Treatment.BLOCK
    address_treatment: Optional[Treatment] = Treatment.BLOCK
    text_treatment: Optional[Treatment] = None
    plate_shape_treatment: Optional[Treatment] = None
    # --- classification
    min_conf_identifier: float = 30.0        # OCR word confidence (0-100) needed to call a word identifier-like (low on purpose)
    min_conf_text: float = 55.0              # ... and to flag ordinary text
    min_text_alpha: int = 3                  # letters needed before a line counts as readable text
    plate_max_line_words: int = 3            # a two-word plate ("ABC 1234") must sit in a short line
    # --- geometry
    region_margin: float = 0.25              # grow every finding box by this fraction per side
    use_plate_shape: bool = True             # look for plate-shaped objects and read them as tight crops
    max_shape_crops: int = 4                 # OCR calls per frame spent on plate-shaped candidates
    # --- temporal behaviour
    max_unseen_scans: int = 2                # a track survives this many scans without a sighting
    extend_frames: int = -1                  # two-pass: frames covered before the first / after the last sighting (-1 = 2*scan_every-1)
    hold_growth: float = 0.03                # live: box growth per frame since the last sighting

    def treatment_for(self, kind: ContextKind) -> Optional[Treatment]:
        return {ContextKind.PLATE: self.plate_treatment, ContextKind.CONTACT: self.contact_treatment,
                ContextKind.ADDRESS: self.address_treatment, ContextKind.TEXT: self.text_treatment,
                ContextKind.PLATE_SHAPE: self.plate_shape_treatment}[kind]

    @property
    def extend(self) -> int:
        return self.extend_frames if self.extend_frames >= 0 else max(0, 2 * self.scan_every - 1)

    def to_dict(self) -> dict:
        d = {k: (v.value if isinstance(v, Treatment) else v) for k, v in self.__dict__.items()}
        d["extend_frames_effective"] = self.extend
        return d


# --------------------------------------------------------------------------------------------- OCR data types
@dataclass(frozen=True)
class OcrWord:
    box: Box
    text: str
    conf: float                              # 0-100


@dataclass
class OcrLine:
    words: list[OcrWord]

    @property
    def box(self) -> Box:
        return _union([w.box for w in self.words])

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(frozen=True)
class ContextFinding:
    """What the scan keeps about a hit: kind, geometry, confidence. Deliberately NOT the recognised text."""
    kind: ContextKind
    box: Box
    conf: float                              # 0-1


@dataclass
class ContextRegion:
    cid: int                                 # context track id (own namespace, not a face track id)
    kind: ContextKind                        # strongest kind seen on this track
    box: Box                                 # final geometry, margin already applied
    treatment: Optional[Treatment]           # None = flagged only, pixels untouched
    held: bool                               # True when not backed by a sighting in this very frame


@dataclass
class ContextFrame:
    regions: list[ContextRegion] = field(default_factory=list)
    new_ids: list[int] = field(default_factory=list)       # tracks first seen this frame (the pipeline backfills them)
    error: bool = False                                     # the scan failed on this frame: the pipeline blocks it
    scanned: bool = False


class OcrEngine(Protocol):
    name: str
    def read(self, frame: np.ndarray) -> list[OcrLine]: ...
    def read_crops(self, crops: Sequence[np.ndarray]) -> list[list[OcrWord]]: ...


def _union(boxes: Sequence[Box]) -> Box:
    return Box(min(b.x1 for b in boxes), min(b.y1 for b in boxes), max(b.x2 for b in boxes), max(b.y2 for b in boxes))


def _contain(a: Box, b: Box) -> float:
    """Fraction of the smaller box that lies inside the other."""
    ix1, iy1, ix2, iy2 = max(a.x1, b.x1), max(a.y1, b.y1), min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    m = min(a.area, b.area)
    return inter / m if m > 0 else 0.0


# --------------------------------------------------------------------------------------------- text classification
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_HANDLE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{3,}")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]{2,}\.(?:com|org|net|br|io|edu|gov|info|co|me)\b(?:/\S*)?", re.I)
_PHONE = re.compile(r"(?<![\w])\+?\(?\d[\d\s().-]{6,}\d(?![\w])")
_STREET_TYPES = (r"street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|terrace|way|place|"
                 r"rua|av|avenida|alameda|travessa|rodovia|estrada")
_ADDRESS = [
    re.compile(rf"\b\d{{1,5}}[A-Za-z]?\s+(?:[A-Za-z.'-]+\s+){{0,3}}(?:{_STREET_TYPES})\b\.?", re.I),          # 742 Evergreen Terrace
    re.compile(rf"\b(?:{_STREET_TYPES})\.?\s+(?:[A-Za-z.'-]+\s+){{0,4}}\d{{1,5}}\b", re.I),                    # Rua das Flores 123
    re.compile(rf"\b(?:[A-Za-z.'-]+\s+){{1,3}}(?:{_STREET_TYPES})\.?\s+\d{{1,5}}\b", re.I),                    # Main Road 133
    re.compile(r"\b(?:sqn|sqs|shis|shin|qnn|qnl|bloco|quadra|lote|apto?|apt|unit|suite)\.?\s*\d{1,4}[A-Za-z]?\b", re.I),
    re.compile(r"(?<!\d)\d{5}-\d{3,4}(?!\d)"),                                                                  # postal codes 12345-678 / 12345-6789
]
_PLATE_PATTERNS = [re.compile(r"[A-Z]{3}\d[A-Z0-9]\d{2}"), re.compile(r"[A-Z0-9]{5,8}")]


def _is_plate_token(tok: str) -> bool:
    t = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
    if not 5 <= len(t) <= 8:
        return False
    if _PLATE_PATTERNS[0].fullmatch(t):
        return True
    letters, digits = sum(c.isalpha() for c in t), sum(c.isdigit() for c in t)
    return letters >= 2 and digits >= 2


def _phone_spans(text: str):
    for m in _PHONE.finditer(text):
        digits = sum(c.isdigit() for c in m.group())
        if 8 <= digits <= 15:
            yield m.span()


def classify_line(line: OcrLine, cfg: ContextConfig) -> list[ContextFinding]:
    """Pure function: OCR line -> findings. The recognised string is used here and dropped."""
    words = [w for w in line.words if w.text.strip()]
    if not words:
        return []
    texts, offs, pos = [], [], 0
    for w in words:
        offs.append((pos, pos + len(w.text)))
        texts.append(w.text)
        pos += len(w.text) + 1
    full = " ".join(texts)
    out: list[ContextFinding] = []
    used = [False] * len(words)

    def add(kind: ContextKind, idxs: list[int]):
        sel = [words[i] for i in idxs]
        if not sel or max(w.conf for w in sel) < cfg.min_conf_identifier:
            return
        out.append(ContextFinding(kind, _union([w.box for w in sel]), float(np.mean([w.conf for w in sel])) / 100.0))
        for i in idxs:
            used[i] = True

    def words_in(span) -> list[int]:
        return [i for i, (a, b) in enumerate(offs) if a < span[1] and b > span[0]]

    for rx in (_EMAIL, _HANDLE, _URL):
        for m in rx.finditer(full):
            add(ContextKind.CONTACT, words_in(m.span()))
    for sp in _phone_spans(full):
        add(ContextKind.CONTACT, words_in(sp))
    for rx in _ADDRESS:
        for m in rx.finditer(full):
            add(ContextKind.ADDRESS, words_in(m.span()))
    for i in range(len(words)):                      # a lone plate-like token counts in any line (OCR merges unrelated words on one row)
        if used[i]:
            continue
        if _is_plate_token(words[i].text):
            add(ContextKind.PLATE, [i])
        elif len(words) <= cfg.plate_max_line_words and i + 1 < len(words) and not used[i + 1] \
                and _is_plate_token(words[i].text + words[i + 1].text):
            add(ContextKind.PLATE, [i, i + 1])         # "ABC 1234": the riskier two-word join only in short lines
    rest = [w for w, u in zip(words, used) if not u]
    alpha = sum(c.isalpha() for w in rest for c in w.text)
    if rest and alpha >= cfg.min_text_alpha and np.mean([w.conf for w in rest]) >= cfg.min_conf_text:
        alnum = sum(c.isalnum() for w in rest for c in w.text)
        if alnum >= 0.6 * sum(len(w.text) for w in rest):
            out.append(ContextFinding(ContextKind.TEXT, _union([w.box for w in rest]), float(np.mean([w.conf for w in rest])) / 100.0))
    return out


def _inside(a: Box, b: Box) -> float:
    """Fraction of `a` that lies inside `b`."""
    ix1, iy1, ix2, iy2 = max(a.x1, b.x1), max(a.y1, b.y1), min(a.x2, b.x2), min(a.y2, b.y2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1) / a.area if a.area > 0 else 0.0


def merge_findings(fs: Sequence[ContextFinding]) -> list[ContextFinding]:
    """Findings that mostly overlap are one thing. Same strength: union box (two OCR passes saw the same text).
    Weaker finding mostly inside a stronger one: dropped (covered). A weaker finding that sticks out stays, so an
    identifier in the middle of a sentence is blocked on its own and the rest of the sentence is still flagged."""
    out: list[ContextFinding] = []
    for f in sorted(fs, key=lambda f: (-_KIND_RANK[f.kind], -f.box.area)):
        for i, o in enumerate(out):
            if _KIND_RANK[f.kind] == _KIND_RANK[o.kind] and _contain(f.box, o.box) >= 0.6:
                out[i] = ContextFinding(o.kind, _union([o.box, f.box]), max(o.conf, f.conf))
                break
            if _KIND_RANK[f.kind] < _KIND_RANK[o.kind] and _inside(f.box, o.box) >= 0.6:
                break
        else:
            out.append(f)
    return out


# --------------------------------------------------------------------------------------------- Tesseract engine
class TesseractOcr:
    """System `tesseract` binary, frames passed over stdin as PNG (RAM only, no temp files).

    Measured in run 006 (docs/16): sparse mode (`--psm 11`) reads almost nothing but large signs; `--psm 6` and `--psm 3`
    do the work, and the union of both beats either. Each pass costs roughly 0.2 s per 800x560 frame on one CPU core."""
    name = "tesseract"

    def __init__(self, lang: str = "eng", passes: Sequence[tuple[int, float]] = ((6, 1.0), (3, 1.0)),
                 binary: Optional[str] = None, timeout: float = 30.0, workers: Optional[int] = None, max_side: int = 1600):
        self.lang, self.passes, self.timeout, self.max_side = lang, tuple(passes), timeout, max_side
        self.binary = binary or shutil.which("tesseract")
        self.workers = workers or min(4, os.cpu_count() or 1)
        self._env = {**os.environ, "OMP_THREAD_LIMIT": "1"}

    @classmethod
    def check(cls, lang: str = "eng", binary: Optional[str] = None) -> str:
        """Raise OcrUnavailable with an actionable message, else return the version line."""
        exe = binary or shutil.which("tesseract")
        if not exe:
            raise OcrUnavailable("tesseract not found on PATH (install it, e.g. `apt install tesseract-ocr` or `brew install tesseract`)")
        try:
            langs = subprocess.run([exe, "--list-langs"], capture_output=True, timeout=20)
            ver = subprocess.run([exe, "--version"], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as e:
            raise OcrUnavailable(f"tesseract could not be run: {e}") from e
        have = set(langs.stdout.decode(errors="replace").split()[1:]) | set(langs.stderr.decode(errors="replace").split()[1:])
        missing = [l for l in lang.split("+") if l not in have]
        if missing:
            raise OcrUnavailable(f"tesseract language data missing: {', '.join(missing)} (installed: {', '.join(sorted(have)) or 'none'})")
        return (ver.stdout or ver.stderr).decode(errors="replace").splitlines()[0]

    def _tsv(self, gray: np.ndarray, psm: int) -> list[list[str]]:
        ok, buf = cv2.imencode(".png", gray)
        if not ok:
            raise OcrError("could not encode frame for OCR")
        try:
            r = subprocess.run([self.binary, "stdin", "stdout", "--psm", str(psm), "-l", self.lang, "tsv"],
                               input=buf.tobytes(), capture_output=True, env=self._env, timeout=self.timeout)
        except (OSError, subprocess.SubprocessError) as e:
            raise OcrError(f"tesseract failed: {e}") from e
        if r.returncode != 0:
            raise OcrError(f"tesseract exited with {r.returncode}")
        return [l.split("\t") for l in r.stdout.decode(errors="replace").splitlines()[1:]]

    @staticmethod
    def _lines(rows: list[list[str]], scale: float) -> list[OcrLine]:
        groups: dict[tuple, list[OcrWord]] = {}
        for c in rows:
            if len(c) < 12 or c[0] != "5" or not c[11].strip():
                continue
            try:
                x, y, w, h, conf = int(c[6]), int(c[7]), int(c[8]), int(c[9]), float(c[10])
            except ValueError:
                continue
            if conf < 0:
                continue
            groups.setdefault((c[2], c[3], c[4]), []).append(OcrWord(Box(x / scale, y / scale, (x + w) / scale, (y + h) / scale), c[11], conf))
        return [OcrLine(sorted(ws, key=lambda w: w.box.x1)) for ws in groups.values()]

    def read(self, frame: np.ndarray) -> list[OcrLine]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        lines: list[OcrLine] = []
        for psm, scale in self.passes:
            s = min(scale, self.max_side / max(gray.shape[:2]))
            g = gray if abs(s - 1.0) < 1e-6 else cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
            lines += self._lines(self._tsv(g, psm), s)
        return lines

    def read_crops(self, crops: Sequence[np.ndarray]) -> list[list[OcrWord]]:
        def one(c: np.ndarray) -> list[OcrWord]:
            fill = int(np.median(c))
            padded = cv2.copyMakeBorder(c, 12, 12, 20, 20, cv2.BORDER_CONSTANT, value=fill)
            return [w for ln in self._lines(self._tsv(padded, 7), 1.0) for w in ln.words]
        if not crops:
            return []
        if self.workers <= 1 or len(crops) == 1:
            return [one(c) for c in crops]
        with ThreadPoolExecutor(self.workers) as ex:
            return list(ex.map(one, crops))


class ScriptedOcr:
    """Test/demo OCR driven by a per-call script. `lines[i]` is returned by the i-th `read()` call;
    `crop_words` is returned (in order) by `read_crops`."""
    name = "scripted-ocr"

    def __init__(self, lines: Optional[dict[int, list[OcrLine]]] = None, crop_words: Optional[list[list[OcrWord]]] = None,
                 fail_on: Sequence[int] = ()):
        self.lines, self.crop_words, self.fail_on = lines or {}, crop_words or [], set(fail_on)
        self.calls = 0

    def read(self, frame: np.ndarray) -> list[OcrLine]:
        i, self.calls = self.calls, self.calls + 1
        if i in self.fail_on:
            raise OcrError("scripted failure")
        return list(self.lines.get(i, []))

    def read_crops(self, crops: Sequence[np.ndarray]) -> list[list[OcrWord]]:
        return [self.crop_words[i] if i < len(self.crop_words) else [] for i in range(len(crops))]


# --------------------------------------------------------------------------------------------- plate-shape finder
@dataclass
class ShapeCandidate:
    box: Box                                 # axis-aligned bounding box in the frame
    crop: np.ndarray                         # deskewed grayscale crop, 44 px high


def _order(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def _deskew(gray: np.ndarray, rect, pad: float = 0.12, target_h: int = 44) -> np.ndarray:
    pts = _order(cv2.boxPoints(rect))
    w_e, h_e = np.linalg.norm(pts[1] - pts[0]), np.linalg.norm(pts[2] - pts[1])
    if h_e > w_e:                                         # long side is vertical: start from the next corner
        pts, w_e, h_e = np.roll(pts, -1, axis=0), h_e, w_e
    c = pts.mean(0)
    pts = c + (pts - c) * (1 + pad)
    w_e, h_e = w_e * (1 + pad), h_e * (1 + pad)
    wd = int(max(16, w_e * target_h / max(h_e, 1.0)))
    m = cv2.getPerspectiveTransform(pts, np.array([[0, 0], [wd, 0], [wd, target_h], [0, target_h]], np.float32))
    return cv2.warpPerspective(gray, m, (wd, target_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _char_blobs(crop: np.ndarray) -> int:
    """Number of character-sized blobs of similar height (best of dark-on-light / light-on-dark)."""
    _, b = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    h, best = crop.shape[0], 0
    for img in (b, 255 - b):
        n, _, st, _ = cv2.connectedComponentsWithStats(img)
        hs = [st[i, 3] for i in range(1, n) if 0.3 * h <= st[i, 3] <= 0.95 * h and st[i, 2] <= 1.2 * h and st[i, 4] >= 0.04 * h * h]
        if len(hs) >= 4 and np.std(hs) / np.mean(hs) < 0.25:
            best = max(best, len(hs))
    return best


def find_plate_shapes(frame: np.ndarray, max_candidates: int = 80) -> list[ShapeCandidate]:
    """Plate-shaped candidates: rectangles with aspect 1.8-7 holding 4-10 similar character-sized blobs. Geometry only."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    h, w = gray.shape[:2]
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for c in cnts:
        rect = cv2.minAreaRect(c)
        rw, rh = max(rect[1]), min(rect[1])
        if rh < 6 or not (0.0003 <= rw * rh / (w * h) <= 0.06) or not (1.8 <= rw / rh <= 7.0):
            continue
        rects.append((rw * rh, rect))
    rects.sort(key=lambda t: -t[0])
    kept: list = []
    out: list[ShapeCandidate] = []
    for _, rect in rects[:max_candidates]:
        if any(np.hypot(rect[0][0] - k[0][0], rect[0][1] - k[0][1]) <= 0.4 * max(rect[1]) for k in kept):
            continue
        crop = _deskew(gray, rect)
        if not (4 <= _char_blobs(crop) <= 10):
            continue
        kept.append(rect)
        pts = cv2.boxPoints(rect)
        out.append(ShapeCandidate(Box(float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())), crop))
    return out


# --------------------------------------------------------------------------------------------- the scanner
def _reads_as_plain_text(words: Sequence[OcrWord], cfg: ContextConfig) -> bool:
    """A crop that OCR read with good confidence as mostly letters (a shop sign) is not an 'unread plate'."""
    ws = [w for w in words if w.text.strip()]
    if not ws:
        return False
    chars = "".join(w.text for w in ws)
    alpha = sum(c.isalpha() for c in chars)
    return alpha >= cfg.min_text_alpha and alpha >= 0.8 * len(chars) and float(np.mean([w.conf for w in ws])) >= cfg.min_conf_text + 10


class ContextScanner:
    name = "context-scan-v0"

    def __init__(self, ocr: OcrEngine, cfg: Optional[ContextConfig] = None):
        self.ocr, self.cfg = ocr, cfg or ContextConfig()

    def info(self) -> dict:
        """Facts for the report (no frame content, no text)."""
        return {"scanner": self.name, "ocr_engine": getattr(self.ocr, "name", "?"), "ocr_languages": getattr(self.ocr, "lang", None),
                "ocr_passes": [list(p) for p in getattr(self.ocr, "passes", ())], "plate_shape_search": self.cfg.use_plate_shape}

    def scan_frame(self, frame: np.ndarray) -> list[ContextFinding]:
        """Raises OcrError if the engine fails. Returns findings carrying no recognised text."""
        cfg = self.cfg
        fs: list[ContextFinding] = []
        for line in self.ocr.read(frame):
            fs += classify_line(line, cfg)
        fs = merge_findings(fs)
        if cfg.use_plate_shape and cfg.max_shape_crops > 0:
            plates = [f.box for f in fs if f.kind in IDENTIFIER_KINDS]
            # NOTE: candidates inside a TEXT box are deliberately NOT skipped: OCR merges unrelated words on one row into one wide
            # line, and a plate sitting in that row would then go unread (found by the real-OCR test in run 006).
            cands = [c for c in find_plate_shapes(frame) if not any(_contain(c.box, p) >= 0.5 for p in plates)][:cfg.max_shape_crops]
            for cand, words in zip(cands, self.ocr.read_crops([c.crop for c in cands])):
                hits = [f for f in classify_line(OcrLine(list(words)), cfg) if f.kind in IDENTIFIER_KINDS] if words else []
                if hits:
                    fs.append(ContextFinding(max(hits, key=lambda f: _KIND_RANK[f.kind]).kind, cand.box, max(f.conf for f in hits)))
                elif not _reads_as_plain_text(words, cfg):
                    fs.append(ContextFinding(ContextKind.PLATE_SHAPE, cand.box, 0.3))     # a sign that reads cleanly is not an unread plate
            fs = merge_findings(fs)
        return fs


# --------------------------------------------------------------------------------------------- tracks
@dataclass
class ContextTrack:
    cid: int
    kinds: set = field(default_factory=set)
    sightings: list = field(default_factory=list)          # [(frame_idx, Box)]
    last_scan: int = 0

    @property
    def kind(self) -> ContextKind:
        return max(self.kinds, key=lambda k: _KIND_RANK[k])

    def treatment(self, cfg: ContextConfig) -> Optional[Treatment]:
        """Strongest treatment of any kind seen on the track: a track never gets weaker."""
        best: Optional[Treatment] = None
        for k in self.kinds:
            t = cfg.treatment_for(k)
            if t is not None:
                best = t if best is None else stronger(best, t)
        return best


class _Linker:
    """Associates findings with tracks by overlap. Shared by the live source and the offline planner."""
    def __init__(self, cfg: ContextConfig):
        self.cfg, self.tracks, self.active, self._next = cfg, {}, [], 0

    def update(self, idx: int, findings: Sequence[ContextFinding]) -> list[int]:
        cfg = self.cfg
        horizon = cfg.max_unseen_scans * cfg.scan_every + 1
        self.active = [t for t in self.active if idx - t.last_scan <= horizon]
        pairs = []
        for fi, f in enumerate(findings):
            for t in self.active:
                last = t.sightings[-1][1]
                score = max(f.box.iou(last), 0.8 * _contain(f.box, last))
                if score < 0.15:
                    # No overlap: a fast mover can travel a whole box width between scans. Fall back to centre distance, but
                    # only for similar-sized boxes, and rank below every overlap match.
                    dx, dy = f.box.center[0] - last.center[0], f.box.center[1] - last.center[1]
                    lim = 1.5 * max(f.box.w, last.w)
                    ratio = f.box.area / last.area if last.area > 0 else 0.0
                    score = 0.1 * (1 - (dx * dx + dy * dy) ** 0.5 / lim) if (0.33 <= ratio <= 3.0 and (dx * dx + dy * dy) ** 0.5 <= lim) else 0.0
                    if score <= 0.0:
                        continue
                pairs.append((score, fi, t))
        pairs.sort(key=lambda p: -p[0])
        done_f, done_t, new_ids = set(), set(), []
        for _, fi, t in pairs:
            if fi in done_f or t.cid in done_t:
                continue
            done_f.add(fi); done_t.add(t.cid)
            t.kinds.add(findings[fi].kind); t.sightings.append((idx, findings[fi].box)); t.last_scan = idx
        for fi, f in enumerate(findings):
            if fi in done_f:
                continue
            t = ContextTrack(self._next, {f.kind}, [(idx, f.box)], idx)
            self._next += 1
            self.tracks[t.cid] = t
            self.active.append(t)
            new_ids.append(t.cid)
        return new_ids


def _grow(b: Box, frac: float, w: int, h: int) -> Box:
    return b.expanded(frac, w, h)


# --------------------------------------------------------------------------------------------- live source
class LiveContext:
    """Streaming source: scan every `scan_every` frames, hold regions between scans (constant-velocity guess, growing box)."""
    def __init__(self, scanner: ContextScanner):
        self.scanner, self.cfg = scanner, scanner.cfg
        self.name = scanner.name
        self.info = scanner.info()
        self.linker = _Linker(self.cfg)
        self.scans = self.scan_errors = 0

    def _box_at(self, t: ContextTrack, idx: int, w: int, h: int) -> Box:
        f1, b1 = t.sightings[-1]
        dt = idx - f1
        shift = (0.0, 0.0)
        if len(t.sightings) >= 2 and dt > 0:
            f0, b0 = t.sightings[-2]
            if f1 > f0:
                vx, vy = (b1.center[0] - b0.center[0]) / (f1 - f0), (b1.center[1] - b0.center[1]) / (f1 - f0)
                shift = (max(-b1.w, min(b1.w, vx * dt)), max(-b1.h, min(b1.h, vy * dt)))
        return _grow(b1.shifted(*shift), self.cfg.region_margin + self.cfg.hold_growth * dt, w, h)

    def frame(self, idx: int, frame: np.ndarray) -> ContextFrame:
        h, w = frame.shape[:2]
        cf = ContextFrame()
        if idx % self.cfg.scan_every == 0:
            cf.scanned = True
            self.scans += 1
            try:
                cf.new_ids = self.linker.update(idx, self.scanner.scan_frame(frame))
            except Exception:                                   # any scan failure fails closed: the frame is blocked
                cf.error, self.scan_errors = True, self.scan_errors + 1
        for t in self.linker.active:
            tr = t.treatment(self.cfg)
            seen = t.sightings[-1][0] == idx
            cf.regions.append(ContextRegion(t.cid, t.kind, self._box_at(t, idx, w, h), tr, held=not seen))
        return cf


# --------------------------------------------------------------------------------------------- offline plan
@dataclass
class ContextPlan:
    n_frames: int
    size: tuple[int, int]
    scanner_name: str
    scan_every: int
    scanned_frames: int
    error_frames: set
    regions: list                                           # per frame: list[ContextRegion]
    tracks: dict                                            # cid -> {"kind","first","last","sightings"}
    fingerprints: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)


def build_context_plan(results: dict[int, Optional[list[ContextFinding]]], n_frames: int, size: tuple[int, int],
                       cfg: ContextConfig, scanner_name: str, fingerprints: Optional[list] = None,
                       info: Optional[dict] = None) -> ContextPlan:
    """`results[i]` is the findings for scanned frame i, or None when the scan FAILED on that frame.
    Frames not in `results` were not scanned. Gaps are interpolated from both sides; tracks are extended at both ends."""
    w, h = size
    linker = _Linker(cfg)
    errors = {i for i, r in results.items() if r is None}
    for i in sorted(k for k, r in results.items() if r is not None):
        linker.update(i, results[i])
    regions: list[list[ContextRegion]] = [[] for _ in range(n_frames)]
    tinfo, interp, ext_frames = {}, 0, 0
    for t in linker.tracks.values():
        tr = t.treatment(cfg)
        s = t.sightings
        at: dict[int, tuple[Box, bool]] = {}
        for k, (f, b) in enumerate(s):
            at[f] = (b, False)
            if k + 1 < len(s):
                f2, b2 = s[k + 1]
                for g in range(f + 1, f2):
                    u = (g - f) / (f2 - f)
                    at[g] = (Box(*[a + (c - a) * u for a, c in zip((b.x1, b.y1, b.x2, b.y2), (b2.x1, b2.y1, b2.x2, b2.y2))]), True)
                    interp += 1
        e = cfg.extend
        for d in range(1, e + 1):
            for g, ref in ((s[0][0] - d, s[0][1]), (s[-1][0] + d, s[-1][1])):
                if 0 <= g < n_frames and g not in at:
                    at[g] = (_grow(ref, cfg.hold_growth * d, w, h), True)
                    ext_frames += 1
        for g, (b, held) in at.items():
            if 0 <= g < n_frames:
                regions[g].append(ContextRegion(t.cid, t.kind, _grow(b, cfg.region_margin, w, h), tr, held))
        tinfo[t.cid] = {"kind": t.kind.value, "first": min(at), "last": max(at), "sightings": len(s)}
    summary = {"tracks": len(linker.tracks), "interpolated_frames": interp, "extension_frames": ext_frames,
               "scan_errors": len(errors)}
    return ContextPlan(n_frames, size, scanner_name, cfg.scan_every, len(results), errors, regions, tinfo, list(fingerprints or []), summary, dict(info or {}))


class PlannedContext:
    """Replays a ContextPlan (recorded files, two-pass)."""
    def __init__(self, plan: ContextPlan, cfg: ContextConfig):
        self.plan, self.cfg, self.name = plan, cfg, plan.scanner_name
        self.scans, self.scan_errors = plan.scanned_frames, len(plan.error_frames)
        self.info = plan.info

    def frame(self, idx: int, frame: np.ndarray) -> ContextFrame:
        if idx >= self.plan.n_frames:
            raise IndexError("context plan has fewer frames than the video being rendered")
        regs = list(self.plan.regions[idx])
        return ContextFrame(regs, [], error=idx in self.plan.error_frames, scanned=idx % self.plan.scan_every == 0)
