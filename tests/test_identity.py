import inspect
import numpy as np
import pytest
from privacyfirst.identity import (AGE_BINS, Identity, IdentityAssigner, IdentityLibrary,
                                   generate_stub_library, tone_bin_of)
from privacyfirst.types import Box


def lib():
    return generate_stub_library(seed=1, per_cell=4)


def test_library_roundtrip_validation_and_coverage():
    L = lib()
    L2 = IdentityLibrary.from_json(L.to_json())
    assert [i.id for i in L2.identities] == [i.id for i in L.identities]
    assert set(L.coverage()) == {(t, a) for t in (0, 1, 2) for a in AGE_BINS}
    assert not L.all_vetted
    bad = Identity("x", 9, "adult", False, True, "stub", {})
    with pytest.raises(ValueError):
        IdentityLibrary([bad])
    kid_not_ok = Identity("k", 0, "child", False, True, "stub", {})
    with pytest.raises(ValueError, match="child_ok"):
        IdentityLibrary([kid_not_ok])
    with pytest.raises(ValueError):
        IdentityLibrary.from_json('{"schema_version": 99, "identities": []}')


def test_unvetted_identities_refused_by_default():
    a = IdentityAssigner(lib(), seed=0)
    assert a.assign(1, 0, "adult") is None
    b = IdentityAssigner(lib(), seed=0, allow_unvetted=True)
    assert b.assign(1, 0, "adult") is not None and b.uses_unvetted


def test_assignment_is_persistent_and_collision_free():
    a = IdentityAssigner(lib(), seed=3, allow_unvetted=True)
    ids = {t: a.assign(t, 1, "adult").id for t in range(1, 9)}
    assert len(set(ids.values())) == 8                       # no two active tracks share an identity
    assert all(a.assign(t, 0, "adult").id == i for t, i in ids.items())   # persistent per track
    assert a.assignments == 8


def test_release_frees_identity_and_exhaustion_returns_none():
    a = IdentityAssigner(lib(), seed=3, allow_unvetted=True)
    n_adult = 12
    got = [a.assign(t, 1, "adult") for t in range(1, n_adult + 1)]
    assert all(got) and a.assign(99, 1, "adult") is None     # pool exhausted -> caller must demote
    a.release(1)
    assert a.assign(100, 1, "adult") is not None


def test_minor_and_unknown_age_pools():
    a = IdentityAssigner(lib(), seed=5, allow_unvetted=True)
    kid = a.assign(1, 1, "child"); unk = a.assign(2, 1, "unknown"); adult = a.assign(3, 1, "adult")
    assert kid.age_bin == "child" and kid.child_ok
    assert unk.age_bin == "adult" and unk.child_ok           # never a child-looking face on an unknown-age person
    assert adult.age_bin == "adult"


def test_seed_determinism_and_variation():
    pick = lambda s: IdentityAssigner(lib(), seed=s, allow_unvetted=True).assign(1, 1, "adult").id
    assert pick(7) == pick(7)
    assert len({pick(s) for s in range(20)}) > 1


def test_assign_signature_cannot_see_the_face():
    params = list(inspect.signature(IdentityAssigner.assign).parameters)
    assert params == ["self", "track_id", "tone_bin", "age_bin"]       # coarse bins only: structural guarantee


def test_tone_bins():
    f = np.zeros((100, 100, 3), np.uint8)
    b = Box(10, 10, 90, 90)
    for v, want in ((200, 0), (140, 1), (60, 2)):
        f[:] = v
        assert tone_bin_of(f, b) == want
