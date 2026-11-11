from privacyfirst.tracking import Tracker
from privacyfirst.types import Box
from conftest import det, W, H


def test_ghost_track_survives_dropout_then_expires():
    tr = Tracker(max_ghost_frames=3)
    tr.update([det(Box(10, 10, 30, 30))], W, H)
    for _ in range(3):
        tracks = tr.update([], W, H)
        assert len(tracks) == 1 and tracks[0].is_ghost
    assert tr.update([], W, H) == []          # past max_ghost_frames


def test_track_identity_is_stable_across_motion_and_dropout():
    tr = Tracker()
    ids = set()
    x = 10
    for i in range(12):
        dets = [] if i in (4, 5) else [det(Box(x, 20, x + 20, 40))]
        for t in tr.update(dets, W, H):
            ids.add(t.id)
        x += 3
    assert ids == {1}


def test_two_faces_get_two_ids():
    tr = Tracker()
    tracks = tr.update([det(Box(5, 5, 25, 25)), det(Box(100, 60, 130, 90))], W, H)
    assert {t.id for t in tracks} == {1, 2}


def test_ghost_region_grows_and_follows_velocity():
    tr = Tracker()
    for x in (10, 16, 22):
        tr.update([det(Box(x, 20, x + 20, 40))], W, H)
    before = tr.tracks[0].box
    ghost = tr.update([], W, H)[0].box
    assert ghost.center[0] > before.center[0] and ghost.w >= before.w
