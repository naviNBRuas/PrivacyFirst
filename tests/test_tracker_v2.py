"""Run 004 tracker: identity stability gains and the coverage guarantees that must not be traded for them."""
from privacyfirst.tracking import LegacyIoUTracker, Tracker
from privacyfirst.types import Box
from conftest import det, W, H


def box(x, y=20, s=20):
    return Box(x, y, x + s, y + s)


def ids_over(tracker, script):
    seen = set()
    for dets in script:
        for t in tracker.update(dets, W, H):
            seen.add(t.id)
    return seen


def test_ghost_reassociates_after_fast_move_where_iou_alone_fails():
    # steady face, 2 missed frames, then it reappears 14 px away: IoU < 0.2 but well inside the widened ghost gate
    script = [[det(box(10))]] * 5 + [[], []] + [[det(box(24))]] * 3
    assert len(ids_over(Tracker(), script)) == 1
    assert len(ids_over(LegacyIoUTracker(), script)) == 2           # the run 001-003 tracker fragmented here


def test_velocity_after_ghost_rematch_is_per_frame_not_per_gap():
    tr = Tracker()
    for i in range(5):
        tr.update([det(box(10 + 2 * i))], W, H)
    for _ in range(5):
        tr.update([], W, H)
    tr.update([det(box(10 + 2 * 10))], W, H)                           # kept moving at +2 px/frame
    assert abs(tr.tracks[0].vel[0] - 2.0) < 1.0                        # the old update gave ~ +7 here and the next ghost overshot


def test_live_track_keeps_its_detection_instead_of_a_ghost_taking_it():
    tr = Tracker()
    tr.update([det(box(0)), det(box(60))], W, H)                       # A at 0 (moves), B at 60
    tr.update([det(box(10)), det(box(60))], W, H)
    tr.update([det(box(20))], W, H)                                    # B goes missing -> ghost parked near x=60
    tr.update([det(box(30))], W, H)
    tr.update([det(box(40))], W, H)
    tracks = tr.update([det(box(60))], W, H)                           # A (vel +10) jumps to 60 where B's ghost sits
    live = [t for t in tracks if t.misses == 0]
    ghosts = [t for t in tracks if t.misses > 0]
    assert len(live) == 1 and live[0].id == 1 and len(ghosts) == 1 and ghosts[0].id == 2


def test_ghost_covers_both_stayed_and_kept_moving_hypotheses():
    tr = Tracker()
    for x in (10, 22, 34):
        tr.update([det(box(x))], W, H)
    g = tr.update([], W, H)[0]
    assert g.box.x1 <= 34 and g.box.x2 >= 54                           # stayed where it was last detected (34..54)
    assert g.box.x2 >= 62                                              # ...or kept moving (about +10 px/frame -> ~44..64)


def test_ghost_hull_is_limited_to_hull_max_misses():
    tr = Tracker(hull_max_misses=2)
    for x in (10, 22, 34):
        tr.update([det(box(x))], W, H)
    widths = [tr.update([], W, H)[0].box.w for _ in range(6)]
    assert widths[1] > 20 and widths[3] < widths[1] + 20              # hull stops widening the "stayed" hypothesis past the cap


def test_size_gate_stops_small_face_being_absorbed_by_large_track():
    tr = Tracker()
    tr.update([det(Box(40, 20, 100, 80))], W, H)                       # large face
    tracks = tr.update([det(Box(40, 20, 100, 80)), det(Box(60, 30, 72, 42))], W, H)   # tiny face inside it
    assert len(tracks) == 2


def test_unmatched_low_confidence_detection_still_starts_a_track():
    tr = Tracker()
    tracks = tr.update([det(box(50), conf=0.2)], W, H)
    assert len(tracks) == 1 and tracks[0].conf == 0.2                  # a face is cheap to mask, a miss is not


def test_expired_ghost_is_gone_and_gets_no_region():
    tr = Tracker(max_ghost_frames=3)
    tr.update([det(box(10))], W, H)
    for _ in range(3):
        tr.update([], W, H)
    assert tr.update([], W, H) == []
