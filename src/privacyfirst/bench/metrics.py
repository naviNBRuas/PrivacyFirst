from __future__ import annotations
import numpy as np
from ..pipeline import OutputFrame
from ..types import Box
from .synth import Clip, GTFace, W, H

LEAK_COV = 0.90      # a visible face with less than 90% of its box covered counts as leaked
SEVERE_COV = 0.50


def coverage_mask(out: OutputFrame, shape=(H, W)) -> np.ndarray:
    m = np.zeros(shape, bool)
    if out.scene_treatment or out.full_frame_block:
        m[:] = True
        return m
    for _tid, box, _tr in out.regions:
        x1, y1, x2, y2 = box.clamp_int(shape[1], shape[0])
        m[y1:y2, x1:x2] = True
    return m


def face_coverage(mask: np.ndarray, g: GTFace) -> float:
    x1, y1, x2, y2 = g.box.clamp_int(mask.shape[1], mask.shape[0])
    if x2 <= x1 or y2 <= y1:
        return 1.0
    return float(mask[y1:y2, x1:x2].mean())


def best_region_track(out: OutputFrame, g: GTFace) -> int | None:
    best, tid = 0.1, None
    for t, box, _ in out.regions:
        if t < 0:
            continue
        i = g.box.iou(box)
        if i > best:
            best, tid = i, t
    return tid


def score_clip(clip: Clip, outs: list[OutputFrame], dets_per_frame: list[list]) -> dict:
    face_frames = leaked = severe = det_missed = 0
    frames_with_leak = 0
    covs: list[float] = []
    red_area = 0.0
    ids: dict[int, set[int]] = {}
    for out in outs:
        i = out.idx
        mask = coverage_mask(out)
        red_area += float(mask.mean())
        frame_leak = False
        for g in clip.gt[i]:
            if not g.visible:
                continue
            face_frames += 1
            cov = face_coverage(mask, g)
            covs.append(cov)
            if cov < LEAK_COV:
                leaked += 1; frame_leak = True
            if cov < SEVERE_COV:
                severe += 1
            if not any(g.box.iou(d.box) >= 0.3 for d in dets_per_frame[i]):
                det_missed += 1
            t = best_region_track(out, g)
            if t is not None:
                ids.setdefault(g.id, set()).add(t)
        frames_with_leak += int(frame_leak)
    return {
        "frames": len(outs), "visible_face_frames": face_frames,
        "detector_missed_face_frames": det_missed,
        "leaked_face_frames": leaked, "severe_leaked_face_frames": severe,
        "frames_with_any_leak": frames_with_leak,
        "min_coverage": min(covs) if covs else 1.0,
        "mean_redacted_area_frac": red_area / max(1, len(outs)),
        "track_id_changes": sum(max(0, len(v) - 1) for v in ids.values()),
    }
