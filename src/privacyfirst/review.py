"""Pre-publish review: the data model behind step 5-6 of docs/06-ux-flow.md (run 006). No UI, no pixels.

A `ReviewSession` is built from what a finished run already knows: per-frame risk events, per-person and per-context-region
summaries, the verification status and the metadata result. It holds the reviewer's state and enforces the rules the UX
doc promises, so any front end (CLI, desktop, web) gets them for free and they are unit-tested:

  * Every risk marker must be VIEWED before export. A marker that leaves pixels exposed (a flagged, unredacted region) must also
    be DECIDED: accept it as it is, or escalate it to a redaction.
  * Reviewers can only ESCALATE (blur < mosaic < block). There is no relax, no dismiss. For a minor-risk person the refusal
    names the guardian gate, which does not exist in this build (docs/17, decision D13).
  * Export gate: metadata failure is a hard block; failed verification is a hard block when any minor-risk person is present
    and otherwise needs an explicit acknowledgement; "not run" and placeholder/stub components need acknowledgements.
  * Escalations become `Overrides`, which the pipeline applies on a re-render (escalate-only there as well). Viewed/decided state
    does not survive a re-render: the pixels changed, so the reviewer looks again.
  * Serialisation holds frame numbers, ids, enum values and counts only: no pixels, no recognised text, no file paths.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from .types import STRENGTH, Treatment

REVIEW_VERSION = 1


class MarkerKind(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    GHOST_TRACK = "ghost_track"
    VERIFIER_ESCALATION = "verifier_escalation"
    SCENE_BLOCK = "scene_block"
    CONTEXT_IDENTIFIER = "context_identifier"      # plate/contact/address: redacted
    CONTEXT_FLAGGED = "context_flagged"            # readable text or plate-shaped object left VISIBLE: needs a decision
    CONTEXT_SCAN_ERROR = "context_scan_error"


_EVENT_TO_MARKER = {"low_confidence": MarkerKind.LOW_CONFIDENCE, "ghost_track": MarkerKind.GHOST_TRACK,
                    "verifier_escalation": MarkerKind.VERIFIER_ESCALATION, "scene_block": MarkerKind.SCENE_BLOCK,
                    "context_redacted": MarkerKind.CONTEXT_IDENTIFIER, "context_flagged": MarkerKind.CONTEXT_FLAGGED,
                    "context_scan_error": MarkerKind.CONTEXT_SCAN_ERROR}
_ESCALATIONS = (Treatment.BLUR, Treatment.MOSAIC, Treatment.BLOCK)
_ACKS = ("verification_failed_frames_blocked", "verification_not_run", "placeholder_components")

NOT_COVERED = ["Voice (audio is dropped by default)", "Body, clothing, tattoos, uniforms, logos, name tags",
               "Background and location cues", "Text or plates the OCR cannot read (small, blurred, rotated, other languages)"]


class ReviewError(ValueError):
    pass


class RelaxationNotSupported(ReviewError):
    """Review can only escalate. Un-redacting needs a re-run with a different configuration."""


class GuardianGateRequired(RelaxationNotSupported):
    """Relaxing a minor-risk person needs the guardian gate (docs/05), which is not built yet."""


@dataclass
class Marker:
    id: str
    kind: MarkerKind
    start: int
    end: int                                   # inclusive
    ref_type: str                              # face | context | frame
    ref_id: int                                # track / context id, -1 for frame-level
    treatment: Optional[str]                   # strongest treatment applied inside the segment (None = pixels untouched)
    exposed: bool = False                      # True when the segment leaves content visible: a decision is required
    viewed: bool = False
    decision: Optional[str] = None             # "accepted" | "escalated"

    @property
    def frames(self) -> int:
        return self.end - self.start + 1


@dataclass
class PersonCard:
    track_id: int
    first_frame: int
    last_frame: int
    frames: int
    treatments: dict
    minor_risk: bool
    identity_id: Optional[str] = None
    floor: Optional[str] = None                # reviewer escalation (applied on the next render)


@dataclass
class ContextCard:
    cid: int
    kind: str
    first_frame: int
    last_frame: int
    frames: int
    treatment: Optional[str]                   # strongest applied; None = flagged only
    floor: Optional[str] = None


@dataclass
class Overrides:
    face: dict = field(default_factory=dict)       # track id -> Treatment
    context: dict = field(default_factory=dict)    # context id -> Treatment

    def to_pipeline_kwargs(self) -> dict:
        return {"face_escalations": dict(self.face), "context_escalations": dict(self.context)}


@dataclass
class ExportDecision:
    allowed: bool
    hard_blocks: list
    unviewed_markers: list
    undecided_markers: list
    acks_missing: list

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _stronger_than(new: Treatment, current: Optional[str]) -> bool:
    if current is None:
        return True
    return STRENGTH[new] > STRENGTH[Treatment(current)]


def coalesce(events: list[tuple], merge_gap: int = 5) -> list[Marker]:
    """Per-frame events -> segments. Events of one kind on one subject merge when they are at most `merge_gap` frames apart,
    so a flickering detector yields one marker to review, not hundreds."""
    groups: dict[tuple, list[tuple]] = {}
    for fr, kind, rtype, rid, tr in events:
        if kind in _EVENT_TO_MARKER:
            groups.setdefault((kind, rtype, rid), []).append((fr, tr))
    segs: list[Marker] = []
    for (kind, rtype, rid), evs in groups.items():
        evs.sort(key=lambda e: e[0])
        start = prev = evs[0][0]
        best = evs[0][1]
        for fr, tr in evs[1:] + [(None, None)]:
            if fr is not None and fr - prev <= merge_gap + 1:
                prev = fr
                if tr and (best is None or STRENGTH[Treatment(tr)] > STRENGTH[Treatment(best)]):
                    best = tr
                continue
            mk = _EVENT_TO_MARKER[kind]
            segs.append(Marker("", mk, start, prev, rtype, rid, best, exposed=(mk == MarkerKind.CONTEXT_FLAGGED)))
            if fr is not None:
                start = prev = fr
                best = tr
    segs.sort(key=lambda m: (m.start, m.kind.value, m.ref_id))
    for i, m in enumerate(segs, 1):
        m.id = f"m{i:04d}"
    return segs


@dataclass
class ReviewSession:
    markers: list[Marker]
    people: list[PersonCard]
    context: list[ContextCard]
    verification_status: str = "not_run"
    metadata_ok: Optional[bool] = None
    placeholder_components: bool = False
    not_covered: list = field(default_factory=lambda: list(NOT_COVERED))
    acks: set = field(default_factory=set)
    actions: list = field(default_factory=list)          # audit trail: what was done, never who

    # ---- lookups
    def marker(self, mid: str) -> Marker:
        for m in self.markers:
            if m.id == mid:
                return m
        raise ReviewError(f"no such marker {mid!r}")

    def _person(self, tid: int) -> PersonCard:
        for p in self.people:
            if p.track_id == tid:
                return p
        raise ReviewError(f"no such person track {tid}")

    def _ctx(self, cid: int) -> ContextCard:
        for c in self.context:
            if c.cid == cid:
                return c
        raise ReviewError(f"no such context region {cid}")

    @property
    def has_minor_risk(self) -> bool:
        return any(p.minor_risk for p in self.people)

    def _log(self, kind: str, **kw) -> None:
        self.actions.append({"seq": len(self.actions) + 1, "action": kind, **kw})

    # ---- reviewer actions
    def mark_viewed(self, mid: str) -> None:
        self.marker(mid).viewed = True
        self._log("viewed", marker=mid)

    def decide(self, mid: str, decision: str, treatment: Treatment = Treatment.BLOCK) -> None:
        """Only for markers that leave content visible. 'accepted' keeps it; 'escalated' redacts that region on re-render."""
        m = self.marker(mid)
        if not m.exposed:
            raise ReviewError("only markers that leave content visible need a decision")
        if decision not in ("accepted", "escalated"):
            raise ReviewError("decision must be 'accepted' or 'escalated'")
        if decision == "escalated":
            self.escalate_context(m.ref_id, treatment)
        m.decision, m.viewed = decision, True
        self._log("decided", marker=mid, decision=decision)

    def escalate_person(self, tid: int, treatment: Treatment) -> None:
        p = self._person(tid)
        weakest = min(p.treatments, key=lambda k: STRENGTH[Treatment(k)], default=None)
        if treatment not in _ESCALATIONS:
            raise ReviewError("escalation target must be blur, mosaic or block")
        if not _stronger_than(treatment, p.floor) or not _stronger_than(treatment, weakest):
            raise ReviewError("that is not stronger than what is already applied: review can only escalate")
        p.floor = treatment.value
        self._log("escalate_person", track=tid, to=treatment.value)

    def escalate_context(self, cid: int, treatment: Treatment) -> None:
        c = self._ctx(cid)
        if treatment not in _ESCALATIONS:
            raise ReviewError("escalation target must be blur, mosaic or block")
        if not _stronger_than(treatment, c.floor) or not _stronger_than(treatment, c.treatment):
            raise ReviewError("that is not stronger than what is already applied: review can only escalate")
        c.floor = treatment.value
        self._log("escalate_context", context=cid, to=treatment.value)

    def relax_person(self, tid: int) -> None:
        if self._person(tid).minor_risk:
            raise GuardianGateRequired("relaxing a minor-risk person needs the guardian gate, which is not implemented")
        raise RelaxationNotSupported("review can only escalate in this build")

    def dismiss_context(self, cid: int) -> None:
        self._ctx(cid)
        raise RelaxationNotSupported("review can only escalate: a redacted or flagged region cannot be dismissed (decision D13)")

    def acknowledge(self, name: str) -> None:
        if name not in _ACKS:
            raise ReviewError(f"unknown acknowledgement {name!r}")
        self.acks.add(name)
        self._log("acknowledged", ack=name)

    def overrides(self) -> Overrides:
        o = Overrides()
        for p in self.people:
            if p.floor:
                o.face[p.track_id] = Treatment(p.floor)
        for c in self.context:
            if c.floor:
                o.context[c.cid] = Treatment(c.floor)
        return o

    # ---- the gate
    def required_acks(self) -> list[str]:
        need = []
        if self.verification_status == "failed_frames_blocked" and not self.has_minor_risk:
            need.append("verification_failed_frames_blocked")
        if self.verification_status == "not_run":
            need.append("verification_not_run")
        if self.placeholder_components:
            need.append("placeholder_components")
        return need

    def export_gate(self) -> ExportDecision:
        hard = []
        if self.metadata_ok is False:
            hard.append("metadata_verification_failed")
        if self.verification_status == "failed_frames_blocked" and self.has_minor_risk:
            hard.append("verification_failed_with_minor_risk_people")
        unviewed = [m.id for m in self.markers if not m.viewed]
        undecided = [m.id for m in self.markers if m.exposed and m.decision is None]
        missing = [a for a in self.required_acks() if a not in self.acks]
        return ExportDecision(not (hard or unviewed or undecided or missing), hard, unviewed, undecided, missing)

    # ---- serialisation
    def to_dict(self) -> dict:
        g = self.export_gate()
        return {
            "review_version": REVIEW_VERSION,
            "verification_status": self.verification_status, "metadata_verified_clean": self.metadata_ok,
            "placeholder_components": self.placeholder_components,
            "markers": [{**m.__dict__, "kind": m.kind.value, "frames": m.frames} for m in self.markers],
            "people": [p.__dict__ for p in self.people], "context_regions": [c.__dict__ for c in self.context],
            "not_covered": self.not_covered, "required_acknowledgements": self.required_acks(),
            "acknowledged": sorted(self.acks), "actions": self.actions, "export": g.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewSession":
        if d.get("review_version") != REVIEW_VERSION:
            raise ReviewError(f"unsupported review_version {d.get('review_version')!r}")
        ms = [Marker(**{**{k: v for k, v in m.items() if k != "frames"}, "kind": MarkerKind(m["kind"])}) for m in d["markers"]]
        s = cls(ms, [PersonCard(**p) for p in d["people"]], [ContextCard(**c) for c in d["context_regions"]],
                d["verification_status"], d["metadata_verified_clean"], d["placeholder_components"], list(d["not_covered"]),
                set(d["acknowledged"]), list(d["actions"]))
        return s


def build_session(pipe, report_data: dict, merge_gap: int = 5, carry: Optional[Overrides] = None) -> ReviewSession:
    """From a finished pipeline and its report dict. `carry` = overrides of the previous render, shown as floors."""
    st = pipe.stats
    people = [PersonCard(tid, t["first_frame"], t["last_frame"], t["frames"], {k: v for k, v in t["treatments"].items() if v},
                         bool(t["minor_risk"]), t.get("identity_id")) for tid, t in sorted(st.tracks.items())]
    ctx = [ContextCard(cid, t["kind"], t["first"], t["last"], t["frames"], t["treatment"]) for cid, t in sorted(st.context_tracks.items())]
    if carry:
        for p in people:
            if p.track_id in carry.face:
                p.floor = carry.face[p.track_id].value
        for c in ctx:
            if c.cid in carry.context:
                c.floor = carry.context[c.cid].value
    meta = report_data.get("metadata")
    warns = " ".join(report_data.get("warnings", []))
    placeholder = any(k in warns for k in ("placeholder", "Stub replacer", "stand-in"))
    return ReviewSession(coalesce(st.events, merge_gap), people, ctx, report_data["verification"]["status"],
                         None if meta is None else bool(meta["verified_clean"]), placeholder)
