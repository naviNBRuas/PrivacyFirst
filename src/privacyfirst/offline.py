"""Two-pass recorded mode (ADR 0002, run 004).

Live mode must emit frames as they arrive, so it can only look `lookahead` frames into the future. A recorded file
has no such limit, which closes the biggest known leak (a face first detected N frames after it appeared, KNOWN_LIMITATIONS #2).

Pass 1 (`analyze`): run the detector and the forward tracker over the whole file and keep ONLY geometry: boxes,
confidences, ints. No frame, crop or embedding is retained. A 32-bit fingerprint of a 16x16 thumbnail per frame is kept
so pass 2 can prove it is reading the same video; it cannot be inverted into an image.

Planning (`build_plan`) uses hindsight the live tracker never has:
  * stitch track fragments into one person (fewer identity changes),
  * cover the frames BEFORE a person's first detection (blind periods), bounded by `back_extend`,
  * fill gaps between detections from both sides (interpolation + stay/keep-moving hull) instead of extrapolating blind,
  * apply the strongest age evidence found anywhere on the person to every frame of that person,
  * count a track as "stable" using detections shortly AFTER a frame, so swaps do not start 5 frames late.

Pass 2 (`TwoPassRunner.frames`): the normal RedactionPipeline, but with a `PlannedTracker` that replays the plan. All
policy, swap gates, fallbacks, rendering, residual-face verification and report logic are unchanged and still apply.
Everything fails closed: a source that differs from pass 1, or a frame that failed detection in pass 1, never yields
unredacted output.

What this does NOT fix: a face the detector never sees is still never covered, and a blind period longer than
`back_extend` is only covered for the last `back_extend` frames before the first detection.
"""
from __future__ import annotations
import copy
import dataclasses
import zlib
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional
import cv2
import numpy as np
from .context import ContextPlan, ContextScanner, PlannedContext, build_context_plan
from .detect import Detector
from .pipeline import OutputFrame, RedactionPipeline
from .policy import PolicyConfig
from .tracking import Track, Tracker, _size
from .types import Box, Detection


class PlanMismatchError(RuntimeError):
    """Pass 2 is not reading the same video that pass 1 analysed. Output must not be produced."""


@dataclass
class OfflineConfig:
    back_extend: int = 16               # frames covered before a CONFIRMED person's first detection
    back_extend_unconfirmed: int = 4    # ... before a person seen in fewer than `confirm_hits` frames (likely false positive)
    confirm_hits: int = 3
    confirm_lookahead: int = 5          # hindsight window for the "stable track" hit count
    stitch_max_gap: int = 90            # frames between two fragments that may still be the same person
    stitch_dist_gate: float = 1.0       # in face sizes, plus stitch_gate_per_frame per frame of gap
    stitch_gate_per_frame: float = 0.04
    stitch_gate_max: float = 3.0
    size_ratio: float = 2.2
    growth: float = 0.03                # per-frame box growth while no detection is available (same as the live ghost)
    hull_max: int = 15                  # "stayed near the last/next detection" hypothesis kept this many frames from an end
    extrap_max: int = 15                # constant-velocity hypothesis kept this many frames from an end
    stitch: bool = True
    back: bool = True
    interpolate: bool = True


@dataclass
class Plan:
    n_frames: int
    size: tuple[int, int]
    detector_name: str
    detector_ok: list[bool]
    fingerprints: list[int]
    tracks: list[list[Track]]                 # per frame, planned tracks (geometry only)
    summary: dict = field(default_factory=dict)


def fingerprint(frame: np.ndarray) -> int:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return zlib.crc32(cv2.resize(g, (16, 16), interpolation=cv2.INTER_AREA).tobytes())


# ----------------------------------------------------------------------------- planning helpers
@dataclass
class _Obs:
    f: int
    box: Box
    conf: float
    minor: Optional[float]


@dataclass
class _Tracklet:
    tid: int
    obs: list[_Obs] = field(default_factory=list)
    trailing: dict = field(default_factory=dict)       # frame -> Box (tracker ghost boxes after the last detection)


def _vel(obs: list[_Obs]) -> tuple[float, float]:
    if len(obs) < 2 or obs[-1].f == obs[0].f:
        return 0.0, 0.0
    (x0, y0), (x1, y1) = obs[0].box.center, obs[-1].box.center
    n = obs[-1].f - obs[0].f
    return (x1 - x0) / n, (y1 - y0) / n


def _hull(boxes: list[Box]) -> Box:
    return Box(min(b.x1 for b in boxes), min(b.y1 for b in boxes), max(b.x2 for b in boxes), max(b.y2 for b in boxes))


def _lerp(a: Box, b: Box, u: float) -> Box:
    m = lambda p, q: p + (q - p) * u
    return Box(m(a.x1, b.x1), m(a.y1, b.y1), m(a.x2, b.x2), m(a.y2, b.y2))


def _grow(b: Box, frac: float, w: int, h: int) -> Box:
    return b.expanded(frac, w, h)


def _tracklets(dets_log: list[list[Detection]], ok: list[bool], size: tuple[int, int], tracker: Tracker):
    w, h = size
    tl: dict[int, _Tracklet] = {}
    for i, dets in enumerate(dets_log):
        tracks = tracker.update(dets if ok[i] else [], w, h)
        for t in tracks:
            tk = tl.setdefault(t.id, _Tracklet(t.id))
            if t.misses == 0:
                tk.obs.append(_Obs(i, t.box, t.conf, t.minor_prob))
            else:
                tk.trailing[i] = t.box
    return list(tl.values())


def _stitch(tracklets: list[_Tracklet], cfg: OfflineConfig, size) -> dict[int, int]:
    """Return successor map tid -> tid (A is followed by B). Greedy by cost, one successor/predecessor each."""
    cand = []
    for a in tracklets:
        if not a.obs:
            continue
        va = _vel(a.obs[-4:])
        ca = a.obs[-1].box.center
        for b in tracklets:
            if b is a or not b.obs:
                continue
            gap = b.obs[0].f - a.obs[-1].f
            if gap <= 0 or gap > cfg.stitch_max_gap:
                continue
            sa, sb = _size(a.obs[-1].box), _size(b.obs[0].box)
            if max(sa, sb) / min(sa, sb) > cfg.size_ratio:
                continue
            vb = _vel(b.obs[:4])
            cb = b.obs[0].box.center
            fwd = ((ca[0] + va[0] * gap - cb[0]) ** 2 + (ca[1] + va[1] * gap - cb[1]) ** 2) ** 0.5
            bwd = ((cb[0] - vb[0] * gap - ca[0]) ** 2 + (cb[1] - vb[1] * gap - ca[1]) ** 2) ** 0.5
            d = min(fwd, bwd) / max(sa, sb)
            if d <= min(cfg.stitch_gate_max, cfg.stitch_dist_gate + cfg.stitch_gate_per_frame * gap):
                cand.append((d + 0.01 * gap, a.tid, b.tid))
    nxt: dict[int, int] = {}
    has_pred: set[int] = set()
    for _, a, b in sorted(cand):
        if a not in nxt and b not in has_pred:
            nxt[a] = b
            has_pred.add(b)
    return nxt


def build_plan(dets_log: list[list[Detection]], ok: list[bool], fingerprints: list[int], size: tuple[int, int],
               detector_name: str = "?", cfg: Optional[OfflineConfig] = None,
               tracker: Optional[Tracker] = None) -> Plan:
    cfg = cfg or OfflineConfig()
    w, h = size
    n = len(dets_log)
    tracklets = _tracklets(dets_log, ok, size, tracker or Tracker())
    by_id = {t.tid: t for t in tracklets}
    nxt = _stitch(tracklets, cfg, size) if cfg.stitch else {}
    has_pred = set(nxt.values())
    persons: list[list[_Tracklet]] = []
    for t in tracklets:
        if t.tid in has_pred:
            continue
        chain = [t]
        while chain[-1].tid in nxt:
            chain.append(by_id[nxt[chain[-1].tid]])
        persons.append(chain)

    per_frame: list[dict[int, Track]] = [dict() for _ in range(n)]
    st = {"tracklets": len(tracklets), "persons": 0, "stitched_links": len(nxt), "back_extended_frames": 0,
          "interpolated_gap_frames": 0, "trailing_ghost_frames": 0, "detections": sum(len(x) for x in dets_log)}
    people = []
    for chain in persons:
        obs = sorted((o for t in chain for o in t.obs), key=lambda o: o.f)
        if not obs:
            continue
        minors = [o.minor for o in obs if o.minor is not None]
        people.append((obs, chain[-1], max(minors) if minors else None))
    people.sort(key=lambda p: p[0][0].f)
    st["persons"] = len(people)

    for pid, (obs, last_tl, minor) in enumerate(people, start=1):
        frames: dict[int, tuple[Box, float, int, bool, int]] = {}      # f -> (box, conf, misses, interp_ok, gap_len)
        det_frames = [o.f for o in obs]
        for o in obs:
            frames[o.f] = (o.box, o.conf, 0, False, 0)
        # gaps between consecutive detections: two-sided evidence
        for o0, o1 in zip(obs, obs[1:]):
            gap = o1.f - o0.f - 1
            if gap <= 0:
                continue
            i0 = max(0, obs.index(o0) - 3)
            v0 = _vel(obs[i0:obs.index(o0) + 1])
            j1 = min(len(obs), obs.index(o1) + 4)
            v1 = _vel(obs[obs.index(o1):j1])
            for f in range(o0.f + 1, o1.f):
                d0, d1 = f - o0.f, o1.f - f
                parts = [_lerp(o0.box, o1.box, d0 / (o1.f - o0.f))] if cfg.interpolate else []
                if d0 <= cfg.extrap_max:
                    parts.append(o0.box.shifted(v0[0] * d0, v0[1] * d0))
                if d1 <= cfg.extrap_max:
                    parts.append(o1.box.shifted(-v1[0] * d1, -v1[1] * d1))
                if d0 <= cfg.hull_max:
                    parts.append(o0.box)
                if d1 <= cfg.hull_max:
                    parts.append(o1.box)
                if not parts:                       # very long gap, no hypothesis in range: hold the nearer end
                    parts.append(o0.box if d0 <= d1 else o1.box)
                box = _grow(_hull(parts), cfg.growth * min(d0, d1), w, h)
                frames[f] = (box, min(o0.conf, o1.conf), min(d0, d1), True, gap)
                st["interpolated_gap_frames"] += 1
        # before the first detection
        first = obs[0]
        confirmed = len(obs) >= cfg.confirm_hits
        back = (cfg.back_extend if confirmed else cfg.back_extend_unconfirmed) if cfg.back else 0
        vf = _vel(obs[:4]) if confirmed else (0.0, 0.0)
        for k in range(1, back + 1):
            f = first.f - k
            if f < 0:
                break
            parts = [first.box.shifted(-vf[0] * k, -vf[1] * k)] if k <= cfg.extrap_max else []
            if k <= cfg.hull_max:
                parts.append(first.box)
            if not parts:                           # beyond both hypotheses' range: hold the first detection's box
                parts.append(first.box)
            box = _grow(_hull(parts), cfg.growth * k, w, h)
            if box.area < 4.0:
                break
            frames[f] = (box, 0.0, k, False, 0)
            st["back_extended_frames"] += 1
        # after the last detection: the live tracker's ghost boxes (unchanged geometry)
        for f, b in sorted(last_tl.trailing.items()):
            if f > obs[-1].f and f not in frames:
                frames[f] = (b, 0.0, f - obs[-1].f, False, 0)
                st["trailing_ghost_frames"] += 1
        first_det = det_frames[0]
        det_set = set(det_frames)
        streaks, run = {}, 0
        for f in sorted(frames):
            run = run + 1 if f in det_set and (f - 1) in det_set else (1 if f in det_set else 0)
            streaks[f] = run
        for f, (box, conf, misses, interp, gap) in frames.items():
            hits = sum(1 for d in det_frames if d <= f + cfg.confirm_lookahead) if f >= first_det else 0
            hits = max(hits, 0)
            per_frame[f][pid] = Track(pid, box, (0.0, 0.0), conf, conf if conf else 1.0, hits, misses, -1, minor,
                                      [], interp, gap, streak=streaks[f])
    plan_tracks = [[per_frame[i][k] for k in sorted(per_frame[i])] for i in range(n)]
    return Plan(n, size, detector_name, list(ok), list(fingerprints), plan_tracks, st)


def analyze(frames: Iterable[np.ndarray], detector: Detector, cfg: Optional[OfflineConfig] = None,
            tracker: Optional[Tracker] = None) -> Plan:
    """Pass 1. Reads every frame once, keeps geometry only (never the frame)."""
    dets_log: list[list[Detection]] = []
    ok: list[bool] = []
    fps: list[int] = []
    size = None
    for f in frames:
        size = (f.shape[1], f.shape[0])
        fps.append(fingerprint(f))
        try:
            dets_log.append(list(detector.detect(f)))
            ok.append(True)
        except Exception:                               # fails closed in pass 2: that frame is fully blocked
            dets_log.append([])
            ok.append(False)
    if size is None:
        raise ValueError("no frames to analyse")
    return build_plan(dets_log, ok, fps, size, getattr(detector, "name", "?"), cfg, tracker)


def analyze_context(frames: Iterable[np.ndarray], scanner: ContextScanner) -> ContextPlan:
    """Context pass: scan every `scan_every` frames, keep geometry and fingerprints only (never a frame or recognised text).
    A scan failure is recorded as None and becomes a fully blocked frame in pass 2."""
    results: dict = {}
    fps: list[int] = []
    size = None
    for i, f in enumerate(frames):
        size = (f.shape[1], f.shape[0])
        fps.append(fingerprint(f))
        if i % scanner.cfg.scan_every == 0:
            try:
                results[i] = scanner.scan_frame(f)
            except Exception:
                results[i] = None
    if size is None:
        raise ValueError("no frames to analyse")
    return build_context_plan(results, len(fps), size, scanner.cfg, scanner.name, fps, scanner.info())


# ----------------------------------------------------------------------------- pass 2
class PlannedTracker:
    """Drop-in for Tracker that replays a Plan. Ignores the live detections it is handed."""
    def __init__(self, plan: Plan):
        self.plan = plan
        self.frame_idx = -1
        self.tracks: list[Track] = []

    def update(self, dets, frame_w: int, frame_h: int) -> list[Track]:
        self.frame_idx += 1
        if self.frame_idx >= self.plan.n_frames:
            raise PlanMismatchError("pass 2 has more frames than pass 1")
        self.tracks = [copy.copy(t) for t in self.plan.tracks[self.frame_idx]]
        return list(self.tracks)


class ReplayDetector:
    """Stands in for the detector in pass 2. Frames the detector failed on in pass 1 raise again, so the pipeline's
    normal fail-closed path blocks them."""
    def __init__(self, plan: Plan):
        self.plan = plan
        self.name = f"{plan.detector_name} [two-pass replay]"
        self._i = -1

    def detect(self, frame: np.ndarray):
        self._i += 1
        if self._i < self.plan.n_frames and not self.plan.detector_ok[self._i]:
            raise RuntimeError("detector failed on this frame in pass 1")
        return []


class TwoPassRunner:
    """Usage:
        r = TwoPassRunner(lambda: read_frames(path), detector, policy, ...)
        for out in r.frames(): write(out.frame)
        report = PrivacyReport.build(r.pipeline, name, meta)
    `open_frames` must return a fresh iterator over the same frames each time it is called.
    """
    def __init__(self, open_frames: Callable[[], Iterable[np.ndarray]], detector: Detector,
                 policy: Optional[PolicyConfig] = None, cfg: Optional[OfflineConfig] = None, lookahead: int = 4,
                 tracker: Optional[Tracker] = None, context_scanner: Optional[ContextScanner] = None, **pipeline_kw):
        self.open_frames, self.detector, self.policy, self.cfg = open_frames, detector, policy, cfg
        self.lookahead, self.tracker, self.kw = lookahead, tracker, pipeline_kw
        self.plan: Optional[Plan] = None
        self.context_scanner = context_scanner
        self.context_plan: Optional[ContextPlan] = None
        self.pipeline: Optional[RedactionPipeline] = None
        if self.policy is None:
            self.policy = PolicyConfig()
        if self.policy.swap_dropout_release_streak < 0:       # two-pass mode default (run 005 sweep): hindsight makes early release safe enough
            self.policy = dataclasses.replace(self.policy, swap_dropout_release_streak=3)

    def analyze(self) -> Plan:
        self.plan = analyze(self.open_frames(), self.detector, self.cfg, self.tracker)
        if self.context_scanner is not None:
            self.context_plan = analyze_context(self.open_frames(), self.context_scanner)
            if self.context_plan.n_frames != self.plan.n_frames:
                raise PlanMismatchError("context pass and detection pass read a different number of frames")
        return self.plan

    def frames(self) -> Iterator[OutputFrame]:
        plan = self.plan or self.analyze()
        cplan = self.context_plan if self.context_scanner is not None else None
        kw = dict(self.kw)
        if cplan is not None:
            kw["context"] = PlannedContext(cplan, self.context_scanner.cfg)
        pipe = RedactionPipeline(ReplayDetector(plan), self.policy, lookahead=self.lookahead,
                                 tracker=PlannedTracker(plan), **kw)
        pipe.plan_summary = dict(plan.summary, mode="two_pass", n_frames=plan.n_frames)
        self.pipeline = pipe
        i = 0
        for f in self.open_frames():
            if i >= plan.n_frames or fingerprint(f) != plan.fingerprints[i]:
                raise PlanMismatchError(f"frame {i} differs between pass 1 and pass 2")
            if cplan is not None and fingerprint(f) != cplan.fingerprints[i]:
                raise PlanMismatchError(f"frame {i} differs between the context pass and pass 2")
            i += 1
            yield from pipe.push(f)
        if i != plan.n_frames:
            raise PlanMismatchError(f"pass 2 produced {i} frames, pass 1 analysed {plan.n_frames}")
        yield from pipe.flush()
