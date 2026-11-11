import json
import numpy as np
import pytest
from privacyfirst.context import ContextConfig, ContextScanner, LiveContext, OcrLine, OcrWord, ScriptedOcr
from privacyfirst.detect import ScriptedDetector
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.report import PrivacyReport
from privacyfirst.review import (ContextCard, GuardianGateRequired, Marker, MarkerKind, PersonCard, RelaxationNotSupported,
                                 ReviewError, ReviewSession, build_session, coalesce)
from privacyfirst.types import Box, Detection, Treatment


def ev(frames, kind="low_confidence", rtype="face", rid=1, tr="mosaic"):
    return [(f, kind, rtype, rid, tr) for f in frames]


def session(markers=(), people=(), context=(), **kw):
    return ReviewSession(list(markers), list(people), list(context), **kw)


def person(tid=1, minor=False, treatments=None):
    return PersonCard(tid, 0, 10, 11, treatments or {"mosaic": 11}, minor)


# ------------------------------------------------------------------------------------------------ markers
def test_coalesce_merges_close_events_and_splits_distant_ones():
    ms = coalesce(ev([1, 2, 3, 5, 6, 40, 41]), merge_gap=3)
    assert [(m.start, m.end) for m in ms] == [(1, 6), (40, 41)]
    assert [m.id for m in ms] == ["m0001", "m0002"]


def test_coalesce_keeps_subjects_and_kinds_separate_and_takes_the_strongest_treatment():
    evs = ev([1, 2], rid=1, tr="mosaic") + ev([3], rid=1, tr="block") + ev([1, 2], rid=2) + ev([1], kind="ghost_track")
    ms = coalesce(evs)
    assert len(ms) == 3
    a = [m for m in ms if m.kind == MarkerKind.LOW_CONFIDENCE and m.ref_id == 1][0]
    assert (a.start, a.end, a.treatment) == (1, 3, "block")


def test_only_flagged_context_markers_are_exposed():
    ms = coalesce(ev([1], "context_flagged", "context", 0, None) + ev([1], "context_redacted", "context", 1, "block")
                  + ev([1], "scene_block", "frame", -1, "mosaic"))
    assert {m.kind: m.exposed for m in ms} == {MarkerKind.CONTEXT_FLAGGED: True, MarkerKind.CONTEXT_IDENTIFIER: False,
                                               MarkerKind.SCENE_BLOCK: False}


def test_unknown_events_are_ignored():
    assert coalesce([(1, "something_new", "face", 1, "blur")]) == []


# ------------------------------------------------------------------------------------------------ export gate
def full(**kw):
    return session(coalesce(ev([1, 2]) + ev([5], "context_flagged", "context", 0, None)), [person()],
                   [ContextCard(0, "text", 5, 5, 1, None)], verification_status="passed", metadata_ok=True, **kw)


def test_export_needs_every_marker_viewed_and_every_exposed_marker_decided():
    s = full()
    g = s.export_gate()
    assert not g.allowed and len(g.unviewed_markers) == 2 and len(g.undecided_markers) == 1
    for m in s.markers:
        s.mark_viewed(m.id)
    assert s.export_gate().undecided_markers and not s.export_gate().allowed        # viewing is not deciding
    s.decide([m.id for m in s.markers if m.exposed][0], "accepted")
    assert s.export_gate().allowed


def test_deciding_escalate_creates_an_override_and_counts_as_viewed():
    s = full()
    mid = [m.id for m in s.markers if m.exposed][0]
    s.decide(mid, "escalated")
    assert s.marker(mid).viewed and s.overrides().context == {0: Treatment.BLOCK}


def test_decide_rejects_markers_that_expose_nothing_and_bad_decisions():
    s = full()
    low = [m.id for m in s.markers if not m.exposed][0]
    with pytest.raises(ReviewError):
        s.decide(low, "accepted")
    with pytest.raises(ReviewError):
        s.decide([m.id for m in s.markers if m.exposed][0], "dismissed")


def view_all(s):
    for m in s.markers:
        s.mark_viewed(m.id)
        if m.exposed:
            s.decide(m.id, "accepted")


def test_metadata_failure_is_a_hard_block_that_no_acknowledgement_lifts():
    s = session(verification_status="passed", metadata_ok=False)
    assert s.export_gate().hard_blocks == ["metadata_verification_failed"] and not s.export_gate().allowed


def test_failed_verification_blocks_outright_with_minor_risk_people_and_needs_an_ack_without():
    minor = session(people=[person(minor=True)], verification_status="failed_frames_blocked", metadata_ok=True)
    assert "verification_failed_with_minor_risk_people" in minor.export_gate().hard_blocks
    with pytest.raises(ReviewError):
        minor.acknowledge("nope")
    adult = session(people=[person()], verification_status="failed_frames_blocked", metadata_ok=True)
    assert adult.export_gate().acks_missing == ["verification_failed_frames_blocked"] and not adult.export_gate().allowed
    adult.acknowledge("verification_failed_frames_blocked")
    assert adult.export_gate().allowed


def test_not_run_and_placeholder_components_need_acknowledgements():
    s = session(verification_status="not_run", metadata_ok=True, placeholder_components=True)
    assert set(s.export_gate().acks_missing) == {"verification_not_run", "placeholder_components"}
    s.acknowledge("verification_not_run")
    s.acknowledge("placeholder_components")
    assert s.export_gate().allowed


# ------------------------------------------------------------------------------------------------ escalate-only
def test_people_can_only_be_escalated():
    s = session(people=[person(treatments={"mosaic": 5, "blur": 2})])
    with pytest.raises(ReviewError):
        s.escalate_person(1, Treatment.BLUR)                    # not stronger than the weakest applied (blur)
    s.escalate_person(1, Treatment.MOSAIC)
    with pytest.raises(ReviewError):
        s.escalate_person(1, Treatment.MOSAIC)                  # not stronger than the floor already set
    s.escalate_person(1, Treatment.BLOCK)
    with pytest.raises(ReviewError):
        s.escalate_person(1, Treatment.SWAP)
    assert s.overrides().face == {1: Treatment.BLOCK}


def test_relaxing_is_refused_and_names_the_guardian_gate_for_minors():
    s = session(people=[person(1, minor=True), person(2)], context=[ContextCard(0, "plate_like", 0, 1, 2, "block")])
    with pytest.raises(GuardianGateRequired):
        s.relax_person(1)
    with pytest.raises(RelaxationNotSupported):
        s.relax_person(2)
    with pytest.raises(RelaxationNotSupported):
        s.dismiss_context(0)
    assert not s.overrides().face and not s.overrides().context


def test_context_escalation_must_be_stronger_than_what_is_applied():
    s = session(context=[ContextCard(0, "plate_like", 0, 1, 2, "block"), ContextCard(1, "text", 0, 1, 2, None)])
    with pytest.raises(ReviewError):
        s.escalate_context(0, Treatment.BLOCK)
    s.escalate_context(1, Treatment.MOSAIC)
    assert s.overrides().context == {1: Treatment.MOSAIC}


def test_audit_trail_records_actions_in_order_without_identity():
    s = full()
    s.mark_viewed("m0001")
    s.escalate_person(1, Treatment.BLOCK)
    assert [a["action"] for a in s.actions] == ["viewed", "escalate_person"] and all(set(a) <= {"seq", "action", "marker", "track", "to", "context", "decision", "ack"} for a in s.actions)


# ------------------------------------------------------------------------------------------------ serialisation
def test_roundtrip_preserves_state_and_rejects_other_versions():
    s = full()
    s.mark_viewed("m0001")
    s.escalate_person(1, Treatment.BLOCK)
    s.acknowledge("placeholder_components")
    t = ReviewSession.from_dict(json.loads(s.to_json()))
    assert t.to_dict() == s.to_dict()
    d = s.to_dict()
    d["review_version"] = 99
    with pytest.raises(ReviewError):
        ReviewSession.from_dict(d)


# ------------------------------------------------------------------------------------------------ with a real pipeline run
def texture(i=0, w=160, h=120):
    return np.random.default_rng(i).integers(0, 255, (h, w, 3), dtype=np.uint8)


SIGN = OcrLine([OcrWord(Box(10, 10, 60, 24), "WELCOME", 90)])
PLATE = OcrLine([OcrWord(Box(50, 50, 100, 64), "ABC1D23", 90)])


def make_pipe(**kw):
    face = {i: [Detection(Box(40, 40, 110, 80), 0.3 if i < 3 else 0.9)] for i in range(8)}
    ocr = ScriptedOcr({i: [SIGN, PLATE] for i in range(8)})
    return RedactionPipeline(ScriptedDetector(face), lookahead=2,
                             context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))), **kw)


def drive(pipe):
    out = []
    for i in range(8):
        out += pipe.push(texture())
    return out + pipe.flush()


def test_session_from_a_real_run_has_the_expected_markers_cards_and_no_text():
    pipe = make_pipe()
    drive(pipe)
    rep = PrivacyReport.build(pipe, "x.mp4")
    s = build_session(pipe, rep.data)
    kinds = {m.kind for m in s.markers}
    assert {MarkerKind.LOW_CONFIDENCE, MarkerKind.CONTEXT_FLAGGED, MarkerKind.CONTEXT_IDENTIFIER} <= kinds
    assert len(s.people) == 1 and s.people[0].minor_risk and len(s.context) == 2
    assert s.verification_status == rep.data["verification"]["status"] 
    blob = s.to_json()
    assert "ABC1D23" not in blob and "WELCOME" not in blob


def test_reviewer_escalation_feeds_back_into_a_rerender():
    first = make_pipe()
    out1 = drive(first)
    assert all(np.array_equal(o.frame[12:22, 12:58], texture()[12:22, 12:58]) for o in out1)         # sign visible, flagged only
    s = build_session(first, PrivacyReport.build(first, "x.mp4").data)
    flagged = [m for m in s.markers if m.exposed][0]
    s.decide(flagged.id, "escalated")
    second = make_pipe(**s.overrides().to_pipeline_kwargs())
    out2 = drive(second)
    assert all(o.frame[12:22, 12:58].max() == 0 for o in out2)                                       # now destroyed
    assert second.stats.escalations_applied > 0
    s2 = build_session(second, PrivacyReport.build(second, "x.mp4").data, carry=s.overrides())
    assert s2.context[[c.cid for c in s2.context].index(flagged.ref_id)].floor == "block"
    assert not any(m.viewed for m in s2.markers)                                                      # the reviewer looks again
