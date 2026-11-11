"""Trackers with ghost tracks: `Tracker` (run 004, default) and `LegacyIoUTracker` (runs 001-003, kept for A/B).

Ghost tracks are the core fail-closed mechanism for detector dropouts: when a
face stops being detected, the track keeps emitting a predicted region (growing
slightly each frame) for `max_ghost_frames`, so the region stays redacted.

Phase 1 uses a deliberately simple tracker. Phase 2 swaps in ByteTrack/OC-SORT
plus ephemeral appearance re-ID; the interface (update -> list[Track]) stays.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .types import Box, Detection


@dataclass
class Track:
    id: int
    box: Box
    vel: tuple[float, float] = (0.0, 0.0)
    conf: float = 0.0
    min_conf: float = 1.0
    hits: int = 1
    misses: int = 0          # consecutive frames without a matching detection
    born_frame: int = 0
    minor_prob: Optional[float] = None
    history: list[tuple[int, Box]] = field(default_factory=list)
    # Recorded (two-pass) mode only: a gap frame bracketed by detections on BOTH sides, so its box is
    # interpolated rather than extrapolated. The swap gate may accept it (policy.swap_interp_max_gap).
    interp_ok: bool = False
    gap_len: int = 0
    streak: int = 0        # consecutive frames with a real detection (0 on any ghost/gap frame); Tracker + two-pass only
    # Run 004 `Tracker` only. `core` = constant-velocity best estimate (used for association); `box` = what is
    # COVERED, which for a ghost is the hull of core and the last detected box (`anchor`), so both "kept moving"
    # and "stopped/reversed" are covered.
    core: Optional[Box] = None
    anchor: Optional[Box] = None

    @property
    def is_ghost(self) -> bool:
        return self.misses > 0


class LegacyIoUTracker:
    """Run 001-003 tracker: greedy IoU only. Kept so benchmarks can show what the upgrade changed."""
    def __init__(self, iou_thresh: float = 0.2, max_ghost_frames: int = 30,
                 ghost_growth: float = 0.03, vel_smooth: float = 0.6):
        self.iou_thresh = iou_thresh
        self.max_ghost_frames = max_ghost_frames
        self.ghost_growth = ghost_growth
        self.vel_smooth = vel_smooth
        self.tracks: list[Track] = []
        self._next_id = 1
        self.frame_idx = -1

    def _predict(self, t: Track) -> Box:
        return t.box.shifted(*t.vel)

    def update(self, dets: list[Detection], frame_w: int, frame_h: int) -> list[Track]:
        self.frame_idx += 1
        preds = {t.id: self._predict(t) for t in self.tracks}
        # Greedy IoU matching, best pairs first.
        pairs = sorted(
            ((preds[t.id].iou(d.box), ti, di)
             for ti, t in enumerate(self.tracks) for di, d in enumerate(dets)),
            reverse=True)
        used_t: set[int] = set()
        used_d: set[int] = set()
        for iou, ti, di in pairs:
            if iou < self.iou_thresh:
                break
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            t, d = self.tracks[ti], dets[di]
            cx0, cy0 = t.box.center
            cx1, cy1 = d.box.center
            a = self.vel_smooth
            t.vel = (a * (cx1 - cx0) + (1 - a) * t.vel[0], a * (cy1 - cy0) + (1 - a) * t.vel[1])
            t.box, t.conf, t.hits, t.misses = d.box, d.conf, t.hits + 1, 0
            t.min_conf = min(t.min_conf, d.conf)
            if d.minor_prob is not None:
                t.minor_prob = d.minor_prob if t.minor_prob is None else max(t.minor_prob, d.minor_prob)
        # Unmatched tracks become / stay ghosts.
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.misses += 1
                grown = self._predict(t).expanded(self.ghost_growth, frame_w, frame_h)
                t.box = grown
                t.conf = 0.0
        # New tracks from unmatched detections.
        for di, d in enumerate(dets):
            if di not in used_d:
                self.tracks.append(Track(self._next_id, d.box, conf=d.conf, min_conf=d.conf,
                                         born_frame=self.frame_idx, minor_prob=d.minor_prob,
                                         core=d.box, anchor=d.box, streak=1))
                self._next_id += 1
        for t in self.tracks:
            t.history.append((self.frame_idx, t.box))
            del t.history[:-64]
        self.tracks = [t for t in self.tracks if t.misses <= self.max_ghost_frames]
        return list(self.tracks)


def _size(b: Box) -> float:
    return max(1.0, (b.w * b.h) ** 0.5)


class Tracker:
    """Two-stage association tracker with ghost tracks (run 004).

    Differences from LegacyIoUTracker, each aimed at identity stability without weakening coverage:
      * Matching score = IoU plus a centre-distance term, so fast motion (IoU ~ 0) still associates.
      * Live tracks claim detections before ghosts do (a ghost cannot steal a live track's face).
      * Ghost gate widens with the number of missed frames (a ghost's box has been growing and drifting).
      * Detections are matched in two stages, high confidence first (ByteTrack idea); low-confidence ones may
        still extend a track. Unmatched detections of ANY confidence start a track: a face is cheap to mask,
        a miss is not.
      * A size-consistency check stops a small face from being absorbed by a large neighbour's track.
      * A ghost COVERS the hull of its velocity-predicted box and the last detected box (see Track.core/anchor), so
        a face that stopped or reversed while undetected is still inside the redaction.
    Ghost geometry (prediction + growth per missed frame) is unchanged from run 003, so coverage is not weakened.
    """

    def __init__(self, iou_thresh: float = 0.2, max_ghost_frames: int = 30, ghost_growth: float = 0.03,
                 vel_smooth: float = 0.6, high_conf: float = 0.5, dist_gate: float = 0.6,
                 ghost_gate_per_miss: float = 0.06, ghost_gate_max: float = 2.0, size_ratio: float = 2.2,
                 ghost_hull: bool = True, hull_max_misses: int = 15):
        self.iou_thresh, self.max_ghost_frames, self.ghost_growth = iou_thresh, max_ghost_frames, ghost_growth
        self.vel_smooth, self.high_conf = vel_smooth, high_conf
        self.dist_gate, self.ghost_gate_per_miss, self.ghost_gate_max = dist_gate, ghost_gate_per_miss, ghost_gate_max
        self.size_ratio = size_ratio
        self.ghost_hull, self.hull_max_misses = ghost_hull, hull_max_misses
        self.tracks: list[Track] = []
        self._next_id = 1
        self.frame_idx = -1

    def _predict(self, t: Track) -> Box:
        return (t.core or t.box).shifted(*t.vel)

    def _score(self, t: Track, pred: Box, d: Detection) -> float:
        """Association score in (0, 2], or 0 when outside the gate."""
        sr = _size(d.box) / _size(pred)
        if sr > self.size_ratio or sr < 1.0 / self.size_ratio:
            return 0.0
        iou = pred.iou(d.box)
        (px, py), (dx, dy) = pred.center, d.box.center
        dist = ((px - dx) ** 2 + (py - dy) ** 2) ** 0.5 / max(_size(pred), _size(d.box))
        gate = self.dist_gate + (min(self.ghost_gate_max, self.ghost_gate_per_miss * t.misses) if t.misses else 0.0)
        if iou < self.iou_thresh and dist > gate:
            return 0.0
        return iou + max(0.0, 1.0 - dist / max(gate, 1e-6))

    def _match(self, tracks: list[Track], preds: dict, dets: list[Detection], dis: list[int],
               used_t: set, used_d: set) -> None:
        pairs = sorted(((self._score(t, preds[t.id], dets[di]), t.id, di) for t in tracks for di in dis), reverse=True)
        byid = {t.id: t for t in tracks}
        for s, tid, di in pairs:
            if s <= 0.0:
                break
            if tid in used_t or di in used_d:
                continue
            used_t.add(tid)
            used_d.add(di)
            self._apply(byid[tid], dets[di])

    def _apply(self, t: Track, d: Detection) -> None:
        cx0, cy0 = t.box.center
        cx1, cy1 = d.box.center
        a = self.vel_smooth
        # Displacement since the last update spans (misses + 1) frames for a ghost: convert to PER-FRAME velocity.
        # (Run 001-003 treated a k-frame jump as one frame of motion, which made the next ghost overshoot the face.)
        n = t.misses + 1
        t.streak = t.streak + 1 if t.misses == 0 else 1
        t.vel = (a * (cx1 - cx0) / n + (1 - a) * t.vel[0], a * (cy1 - cy0) / n + (1 - a) * t.vel[1])
        t.box, t.conf, t.hits, t.misses = d.box, d.conf, t.hits + 1, 0
        t.core = t.anchor = d.box
        t.min_conf = min(t.min_conf, d.conf)
        if d.minor_prob is not None:
            t.minor_prob = d.minor_prob if t.minor_prob is None else max(t.minor_prob, d.minor_prob)

    def update(self, dets: list[Detection], frame_w: int, frame_h: int) -> list[Track]:
        self.frame_idx += 1
        preds = {t.id: self._predict(t) for t in self.tracks}
        used_t: set[int] = set()
        used_d: set[int] = set()
        hi = [i for i, d in enumerate(dets) if d.conf >= self.high_conf]
        lo = [i for i, d in enumerate(dets) if d.conf < self.high_conf]
        live = [t for t in self.tracks if t.misses == 0]
        ghosts = [t for t in self.tracks if t.misses > 0]
        # Stage 1: high-confidence detections, live tracks first, then ghosts.
        self._match(live, preds, dets, hi, used_t, used_d)
        self._match([t for t in ghosts if t.id not in used_t], preds, dets, hi, used_t, used_d)
        # Stage 2: low-confidence detections may extend whatever is still unmatched.
        rest = [t for t in self.tracks if t.id not in used_t]
        self._match(rest, preds, dets, lo, used_t, used_d)
        # Unmatched tracks become / stay ghosts.
        for t in self.tracks:
            if t.id not in used_t:
                t.misses += 1
                t.streak = 0
                t.core = self._predict(t).expanded(self.ghost_growth, frame_w, frame_h)
                t.conf = 0.0
                t.box = t.core
                if self.ghost_hull and t.anchor is not None and t.misses <= self.hull_max_misses:
                    a = t.anchor.expanded(self.ghost_growth * t.misses, frame_w, frame_h)
                    t.box = Box(min(t.core.x1, a.x1), min(t.core.y1, a.y1), max(t.core.x2, a.x2), max(t.core.y2, a.y2))
        # Unmatched detections (any confidence) start new tracks.
        for di, d in enumerate(dets):
            if di not in used_d:
                self.tracks.append(Track(self._next_id, d.box, conf=d.conf, min_conf=d.conf,
                                         born_frame=self.frame_idx, minor_prob=d.minor_prob,
                                         core=d.box, anchor=d.box))
                self._next_id += 1
        for t in self.tracks:
            t.history.append((self.frame_idx, t.box))
            del t.history[:-64]
        self.tracks = [t for t in self.tracks if t.misses <= self.max_ghost_frames]
        return list(self.tracks)
