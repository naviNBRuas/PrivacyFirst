import ast
import json
from pathlib import Path
import numpy as np
import pytest
from privacyfirst.context import (ContextConfig, ContextFinding, ContextKind, ContextScanner, LiveContext, OcrError, OcrLine,
                                  OcrUnavailable, OcrWord, PlannedContext, ScriptedOcr, TesseractOcr, build_context_plan,
                                  classify_line, find_plate_shapes, merge_findings)
from privacyfirst.detect import ScriptedDetector
from privacyfirst.offline import PlanMismatchError, TwoPassRunner
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.report import PrivacyReport
from privacyfirst.types import Box, Detection, Treatment

CFG = ContextConfig()
HAVE_TESS = True
try:
    TesseractOcr.check()
except OcrUnavailable:
    HAVE_TESS = False
FONT_OK = Path("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf").exists()


def line(text, conf=90.0, y=10.0, x=0.0, wpx=40.0):
    ws, cx = [], x
    for tok in text.split():
        ws.append(OcrWord(Box(cx, y, cx + wpx, y + 14), tok, conf))
        cx += wpx + 6
    return OcrLine(ws)


def kinds(text, conf=90.0):
    return sorted(f.kind.value for f in classify_line(line(text, conf), CFG))


# ------------------------------------------------------------------------------------------------ classification
def test_plates_in_common_formats():
    for t in ("ABC1D23", "ABC-1234", "7ABC123", "ABC1234"):
        assert kinds(t) == ["plate_like"], t
    assert kinds("ABC 1234") == ["plate_like"]                      # two-word plate in a short line


def test_contact_details():
    for t in ("maria.silva@mail.com", "(61) 99876-5432", "+55 61 98765-4321", "555-867-5309", "@some_handle", "www.example.com",
              "https://example.org/x"):
        assert "contact_like" in kinds(t), t


def test_addresses_and_postal_codes():
    for t in ("Rua das Flores 123", "742 Evergreen Terrace", "Main Road 133", "Av. Central 456", "SQN 205", "70000-000"):
        assert "address_like" in kinds(t), t


def test_ordinary_text_is_text_not_identifier():
    for t in ("SCHOOL ZONE", "Open daily", "Welcome home"):
        assert kinds(t) == ["text"], t
    for t in ("12/05/2024", "$1,234,567", "Room", "MP3", "COVID", "ok"):
        assert not set(kinds(t)) & {"plate_like", "contact_like", "address_like"}, t


def test_low_confidence_identifier_ignored_but_low_threshold_catches_weak_reads():
    assert kinds("ABC1D23", conf=20) == []
    assert kinds("ABC1D23", conf=35) == ["plate_like"]            # the identifier threshold is deliberately low


def test_identifier_in_a_sentence_boxes_only_the_identifier():
    fs = classify_line(line("Call me at 61 99876-5432 tomorrow please"), CFG)
    c = [f for f in fs if f.kind == ContextKind.CONTACT][0]
    t = [f for f in fs if f.kind == ContextKind.TEXT][0]
    assert c.box.w < t.box.w                                        # the number is blocked on its own, the rest only flagged


def test_a_lone_plate_token_counts_even_in_a_long_line():
    assert "plate_like" in kinds("SALE TODAY OPEN NOW TMC2O75 HERE")


def test_findings_never_carry_recognised_text():
    assert set(ContextFinding.__dataclass_fields__) == {"kind", "box", "conf"}


def test_merge_same_kind_unions_and_weaker_inside_stronger_is_dropped():
    a = ContextFinding(ContextKind.PLATE, Box(10, 10, 60, 30), 0.9)
    b = ContextFinding(ContextKind.PLATE, Box(12, 11, 64, 31), 0.8)
    t = ContextFinding(ContextKind.TEXT, Box(10, 10, 60, 30), 0.9)
    wide = ContextFinding(ContextKind.TEXT, Box(0, 10, 300, 30), 0.9)
    out = merge_findings([a, b, t, wide])
    assert sorted(f.kind.value for f in out) == ["plate_like", "text"]       # duplicate plate merged, covered text dropped, wide text kept
    assert [f for f in out if f.kind == ContextKind.PLATE][0].box.x2 == 64


# ------------------------------------------------------------------------------------------------ live source
def _frame(i=0, w=160, h=120):
    f = np.full((h, w, 3), 90, np.uint8)
    f[0, 0, 0] = i
    return f


PLATE = OcrLine([OcrWord(Box(50, 50, 100, 64), "ABC1D23", 90)])
SIGN = OcrLine([OcrWord(Box(10, 10, 60, 24), "WELCOME", 90)])


def scanner(lines, every=1, **cfgkw):
    return ContextScanner(ScriptedOcr(lines), ContextConfig(scan_every=every, use_plate_shape=False, **cfgkw))


def test_live_scans_on_cadence_holds_between_scans_and_reports_new_tracks():
    lc = LiveContext(scanner({0: [PLATE], 1: [PLATE]}, every=3))
    f0 = lc.frame(0, _frame())
    assert f0.scanned and f0.new_ids == [0] and not f0.regions[0].held
    f1, f2 = lc.frame(1, _frame()), lc.frame(2, _frame())
    assert not f1.scanned and f1.regions and f1.regions[0].held and f2.regions[0].held
    assert f1.regions[0].treatment == Treatment.BLOCK
    assert f1.regions[0].box.w >= f0.regions[0].box.w               # held boxes only grow
    assert lc.scans == 1


def test_a_track_expires_after_too_many_unseen_scans():
    lc = LiveContext(scanner({0: [PLATE]}, every=1, max_unseen_scans=2))
    lc.frame(0, _frame())
    alive = [bool(lc.frame(i, _frame()).regions) for i in range(1, 6)]
    assert alive[:3] == [True, True, True] and alive[-1] is False


def test_track_treatment_never_weakens_once_an_identifier_was_seen():
    flag_then_plate = {0: [SIGN], 1: [OcrLine([OcrWord(Box(10, 10, 60, 24), "ABC1D23", 90)])]}
    lc = LiveContext(scanner(flag_then_plate, every=1))
    a = lc.frame(0, _frame()).regions[0]
    b = lc.frame(1, _frame()).regions[0]
    assert a.treatment is None and b.treatment == Treatment.BLOCK and a.cid == b.cid
    c = lc.frame(2, _frame()).regions[0]                             # OCR reads nothing now: still blocked
    assert c.held and c.treatment == Treatment.BLOCK


def test_scan_failure_is_reported_as_an_error_frame():
    lc = LiveContext(ContextScanner(ScriptedOcr({}, fail_on=[1]), ContextConfig(scan_every=1, use_plate_shape=False)))
    assert not lc.frame(0, _frame()).error
    assert lc.frame(1, _frame()).error and lc.scan_errors == 1


# ------------------------------------------------------------------------------------------------ planner
def test_plan_interpolates_gaps_extends_ends_and_records_errors():
    cfg = ContextConfig(scan_every=4, extend_frames=2, use_plate_shape=False)
    f = lambda x: [ContextFinding(ContextKind.PLATE, Box(x, 40, x + 40, 60), 0.9)]
    plan = build_context_plan({4: f(20), 8: f(60), 12: None, 16: f(100)}, 24, (200, 100), cfg, "t")
    assert plan.error_frames == {12}
    have = [bool(r) for r in plan.regions]
    assert have[4] and have[8] and have[6]                          # interpolated between sightings
    assert have[4 - cfg.extend] and have[16 + cfg.extend]           # extended before the first / after the last sighting
    assert not have[0] and not have[23]
    mid = plan.regions[6][0].box                                    # halfway between 20 and 60 -> box centred near x=60
    assert 40 < mid.center[0] < 80
    assert len({r.cid for rs in plan.regions for r in rs}) == 1     # one track


def test_a_fast_mover_with_no_box_overlap_between_scans_is_still_one_track():
    cfg = ContextConfig(scan_every=4, use_plate_shape=False)
    f = lambda x: [ContextFinding(ContextKind.PLATE, Box(x, 40, x + 40, 60), 0.9)]
    plan = build_context_plan({0: f(0), 4: f(50), 8: f(100)}, 12, (200, 100), cfg, "t")
    assert plan.summary["tracks"] == 1 and plan.summary["interpolated_frames"] == 6
    two = build_context_plan({0: f(0) + f(120), 4: f(50) + f(170)}, 8, (300, 100), cfg, "t")
    assert two.summary["tracks"] == 2                              # two separate items stay separate


def test_plan_applies_the_strongest_treatment_to_the_whole_track():
    cfg = ContextConfig(scan_every=1, use_plate_shape=False)
    tx = ContextFinding(ContextKind.TEXT, Box(10, 10, 60, 30), 0.9)
    pl = ContextFinding(ContextKind.PLATE, Box(10, 10, 60, 30), 0.9)
    plan = build_context_plan({0: [tx], 1: [tx], 2: [pl], 3: [tx]}, 4, (100, 50), cfg, "t")
    assert [plan.regions[i][0].treatment for i in range(4)] == [Treatment.BLOCK] * 4     # even before the plate was read


# ------------------------------------------------------------------------------------------------ pipeline
def texture_frame(i=0, w=160, h=120):
    rng = np.random.default_rng(i)
    f = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    return f


def std(frame, box):
    x1, y1, x2, y2 = (int(v) for v in (box.x1, box.y1, box.x2, box.y2))
    return float(frame[y1:y2, x1:x2].astype(np.float32).std())


def run(pipe, n):
    out = []
    for i in range(n):
        out += pipe.push(texture_frame(0))
    return out + pipe.flush()


def test_identifier_is_destroyed_and_flagged_text_is_untouched():
    ocr = ScriptedOcr({i: [PLATE, SIGN] for i in range(6)})
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=2, context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    out = run(pipe, 6)
    src = texture_frame(0)
    assert all(std(o.frame, Box(52, 52, 98, 62)) == 0 for o in out)                       # plate region is solid black
    assert all(np.array_equal(o.frame[12:22, 12:58], src[12:22, 12:58]) for o in out)     # flagged sign: pixels unchanged
    assert all(any(c[2] is None for c in o.context_regions) and any(c[2] == "block" for c in o.context_regions) for o in out)


def test_new_context_track_is_backfilled_into_the_lookahead():
    ocr = ScriptedOcr({0: [], 1: [], 2: [PLATE], 3: [PLATE], 4: [PLATE]})
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=4, context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    out = run(pipe, 5)
    assert [std(o.frame, Box(52, 52, 98, 62)) == 0 for o in out] == [True] * 5            # frames 0 and 1 were covered retroactively
    assert pipe.stats.context_backfilled == 2


def test_context_block_wins_over_a_face_treatment_underneath():
    face = {i: [Detection(Box(40, 40, 110, 80), 0.9)] for i in range(4)}
    ocr = ScriptedOcr({i: [PLATE] for i in range(4)})
    pipe = RedactionPipeline(ScriptedDetector(face), lookahead=2, context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    out = run(pipe, 4)
    assert all(std(o.frame, Box(52, 52, 98, 62)) == 0 for o in out)


def test_scan_error_blocks_the_whole_frame_and_is_counted():
    ocr = ScriptedOcr({}, fail_on=[1])
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=2, context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    out = run(pipe, 3)
    assert [o.context_error for o in out] == [False, True, False]
    assert out[1].frame.max() == 0 and out[0].frame.max() > 0
    assert pipe.stats.context_scan_errors == 1


def test_a_crashing_context_source_fails_closed():
    class Boom:
        name = "boom"
        cfg = ContextConfig()
        def frame(self, idx, frame):
            raise RuntimeError("x")
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1, context=Boom())
    out = run(pipe, 2)
    assert all(o.frame.max() == 0 for o in out)


def test_review_escalations_are_escalate_only_and_never_swap():
    ocr = ScriptedOcr({i: [SIGN] for i in range(3)})
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1, context_escalations={0: Treatment.BLOCK},
                             context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    out = run(pipe, 3)
    assert all(std(o.frame, Box(12, 12, 58, 22)) == 0 for o in out)                       # flagged text escalated to a block
    face = {i: [Detection(Box(40, 40, 110, 80), 0.9)] for i in range(3)}
    weak = RedactionPipeline(ScriptedDetector(face), lookahead=1, face_escalations={1: Treatment.BLOCK})
    assert all(set(o.treatments.values()) == {"block"} for o in run(weak, 3))
    with pytest.raises(ValueError):
        RedactionPipeline(ScriptedDetector({}), face_escalations={0: Treatment.SWAP})


# ------------------------------------------------------------------------------------------------ report
def test_report_has_a_keys_only_context_section_and_never_the_text():
    ocr = ScriptedOcr({i: [PLATE, SIGN] for i in range(4)})
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1, context=LiveContext(ContextScanner(ocr, ContextConfig(scan_every=1, use_plate_shape=False))))
    run(pipe, 4)
    rep = PrivacyReport.build(pipe, "x.mp4")
    d = rep.data
    assert d["context_identifier_scan"] == "run_v0_heuristic" and d["context"]["recognised_text_stored"] is False
    assert d["context"]["tracks_redacted"] == 1 and d["context"]["tracks_flagged_only"] == 1
    assert any("NOT redacted" in w for w in d["warnings"]) and any("heuristic OCR" in w for w in d["warnings"])
    blob = rep.to_json() + rep.to_markdown()
    assert "ABC1D23" not in blob and "WELCOME" not in blob


def test_report_without_the_scan_says_not_run():
    pipe = RedactionPipeline(ScriptedDetector({}), lookahead=1)
    run(pipe, 2)
    d = PrivacyReport.build(pipe, "x.mp4").data
    assert d["context_identifier_scan"] == "not_run" and d["context"] is None


# ------------------------------------------------------------------------------------------------ two-pass
def test_two_pass_covers_frames_before_the_first_scan_hit_and_aborts_on_a_different_video():
    frames = [texture_frame(0) for _ in range(12)]
    ocr = ScriptedOcr({3: [PLATE]})                                  # scan every 3: calls are frames 0,3,6,9 -> only call #3 reads the plate
    sc = ContextScanner(ocr, ContextConfig(scan_every=3, use_plate_shape=False))
    runner = TwoPassRunner(lambda: iter(frames), ScriptedDetector({}), context_scanner=sc, lookahead=2)
    out = list(runner.frames())
    covered = [std(o.frame, Box(52, 52, 98, 62)) == 0 for o in out]
    assert covered[9] and covered[9 - sc.cfg.extend] and not covered[0]
    n = {"calls": 0}

    def changing():
        n["calls"] += 1
        return iter(frames if n["calls"] <= 2 else frames[:-1])      # detection pass + context pass see 12 frames, render pass sees 11
    with pytest.raises(PlanMismatchError):
        list(TwoPassRunner(changing, ScriptedDetector({}), context_scanner=ContextScanner(ScriptedOcr({}), ContextConfig(scan_every=3, use_plate_shape=False))).frames())


# ------------------------------------------------------------------------------------------------ structure
def test_context_module_writes_no_files_and_has_no_network_imports():
    src = (Path(__file__).resolve().parents[1] / "src" / "privacyfirst" / "context.py").read_text()
    tree = ast.parse(src)
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    assert not imported & {"tempfile", "socket", "urllib", "http", "requests"}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"imwrite", "write_text", "write_bytes"}      # frames reach tesseract through a pipe only


def test_tesseract_gets_frames_over_stdin_not_as_files(monkeypatch):
    import subprocess
    seen = []

    def fake(args, **kw):
        seen.append((list(args), kw))
        return subprocess.CompletedProcess(args, 0, stdout=b"level\tpage_num\n", stderr=b"")
    monkeypatch.setattr(subprocess, "run", fake)
    ocr = TesseractOcr(binary="/usr/bin/tesseract")
    ocr.read(_frame())
    assert all(a[1] == "stdin" and isinstance(kw["input"], bytes) for a, kw in seen) and seen


def test_missing_engine_or_language_is_reported_not_silently_skipped():
    with pytest.raises(OcrUnavailable):
        TesseractOcr.check(binary="/nonexistent/tesseract")
    if HAVE_TESS:
        with pytest.raises(OcrUnavailable, match="language data missing"):
            TesseractOcr.check("zzz_not_a_language")


def test_cli_fails_loudly_when_the_scan_cannot_run(tmp_path, monkeypatch):
    import cv2
    from privacyfirst.cli import main
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    vw = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 72))
    for _ in range(4):
        vw.write(np.full((72, 96, 3), 100, np.uint8))
    vw.release()
    monkeypatch.setenv("PATH", "/nonexistent")
    assert main(["video", str(src), str(dst), "--context-scan"]) == 2 and not dst.exists()


# ------------------------------------------------------------------------------------------------ real OCR (skipped without tesseract/fonts)
@pytest.mark.skipif(not (HAVE_TESS and FONT_OK), reason="needs tesseract and the Liberation fonts")
def test_real_ocr_covers_identifiers_on_a_clean_synthetic_scene():
    from privacyfirst.bench.contextsynth import VARIANTS, item_mask, make_scene
    f, items = make_scene(7, VARIANTS["clear"])
    cfg = ContextConfig()
    fs = ContextScanner(TesseractOcr(), cfg).scan_frame(f)
    red = np.zeros(f.shape[:2], bool)
    for x in fs:
        if cfg.treatment_for(x.kind) is not None:
            x1, y1, x2, y2 = x.box.expanded(cfg.region_margin, f.shape[1], f.shape[0]).clamp_int(f.shape[1], f.shape[0])
            red[y1:y2, x1:x2] = True
    for it in items:
        m = item_mask(it, f.shape[:2])
        cov = (red & m).sum() / m.sum()
        if it.identifier:
            assert cov >= 0.8, (it.kind, cov)
        else:
            assert cov < 0.3                                          # the ordinary sign is not redacted
    assert any(x.kind == ContextKind.TEXT for x in fs)


@pytest.mark.skipif(not FONT_OK, reason="needs the Liberation fonts")
def test_plate_shape_finder_proposes_the_plate_without_any_ocr():
    from privacyfirst.bench.contextsynth import VARIANTS, make_scene
    f, items = make_scene(3, VARIANTS["clear"])
    plate = [i for i in items if i.kind == "plate"][0]
    assert any(c.box.iou(plate.box) > 0.5 for c in find_plate_shapes(f))
