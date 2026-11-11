"""Context-identifier demo (run 006): invented plate, phone number and sign on a synthetic scene. Needs tesseract + Liberation fonts.

Scene (no real person, plate or number; all text is invented):
  * a "car" drives across the frame carrying a plate (identifier, MOVING),
  * a poster with a phone number (identifier, static, appears at frame 18),
  * a shop sign (ordinary text: FLAGGED, not redacted).
Three renders of the same clip:
  A. live mode        (scan every 3 frames, hold between scans, 4-frame lookahead backfill)
  B. two-pass mode    (whole-file analysis: interpolation between sightings, extension before/after)
  C. two-pass + a reviewer ESCALATING the flagged sign to a block (review model -> overrides -> re-render)
Coverage is measured against ground truth known by construction (the characters of each identifier).
Usage: python scripts/demo_context.py OUT_DIR
"""
import json
import sys
import tempfile
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from privacyfirst.bench.contextsynth import _patch
from privacyfirst.context import ContextConfig, ContextScanner, LiveContext, TesseractOcr
from privacyfirst.detect import ScriptedDetector
from privacyfirst.metadata import strip_video
from privacyfirst.offline import TwoPassRunner
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.report import PrivacyReport
from privacyfirst.review import build_session
from privacyfirst.types import Treatment

W, H, N, FPS = 640, 360, 60, 12
PLATE_TXT, PHONE_TXT, SIGN_TXT = "KQZ4F82", "(99) 91234-5678", "OPEN LATE"
POSTER_FROM = 18


def _paste(img, patch, x, y):
    h, w = patch.shape[:2]
    x, y = int(max(0, min(W - w, x))), int(max(0, min(H - h, y)))
    img[y:y + h, x:x + w] = patch
    return x, y, w, h


def make_clip():
    rng = np.random.default_rng(4)
    plate, pin = _patch("plate", PLATE_TXT, 22, rng)
    phone, phin = _patch("phone", PHONE_TXT, 20, rng)
    sign, sin = _patch("sign", SIGN_TXT, 22, rng)
    frames, gt = [], []
    for t in range(N):
        img = np.zeros((H, W, 3), np.uint8)
        for y in range(H):
            img[y, :] = (80 + y // 6, 110 + y // 9, 120 - y // 14)
        cv2.rectangle(img, (0, 250), (W, H), (70, 70, 75), -1)                          # road
        cx = int(20 + 9 * t)
        cv2.rectangle(img, (cx - 10, 215), (cx + 215, 300), (150, 40, 40), -1)         # car body
        cv2.rectangle(img, (cx + 30, 185), (cx + 170, 220), (120, 30, 30), -1)
        sx, sy, sw, sh = _paste(img, sign, 420, 40)
        items = {"sign": (sx + sin[0], sy + sin[1], sx + sin[2], sy + sin[3])}
        if t >= POSTER_FROM:
            px, py, _, _ = _paste(img, phone, 60, 70)
            items["phone"] = (px + phin[0], py + phin[1], px + phin[2], py + phin[3])
        px, py, _, _ = _paste(img, plate, cx + 62, 255)
        items["plate"] = (px + pin[0], py + pin[1], px + pin[2], py + pin[3])
        img = np.clip(img.astype(np.int16) + rng.integers(-4, 5, img.shape), 0, 255).astype(np.uint8)
        frames.append(img)
        gt.append(items)
    return frames, gt


def coverage(out_frames, gt, kind):
    """Share of frames (where the item exists) in which >= 80% of the item's text pixels were changed to near-black."""
    ok = tot = 0
    for f, items in zip(out_frames, gt):
        if kind not in items:
            continue
        x1, y1, x2, y2 = (int(v) for v in items[kind])
        roi = f[max(0, y1):y2, max(0, x1):x2]
        tot += 1
        ok += int((roi.max(axis=2) < 25).mean() >= 0.8) if roi.size else 0
    return ok, tot


def encode(frames, path):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "r.mp4"
        vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        for f in frames:
            vw.write(f)
        vw.release()
        return strip_video(tmp, Path(path), keep_audio=False)


def render(mode, frames, scanner, overrides=None):
    kw = overrides.to_pipeline_kwargs() if overrides else {}
    if mode == "live":
        pipe = RedactionPipeline(ScriptedDetector({}), lookahead=4, context=LiveContext(scanner), **kw)
        out = []
        for f in frames:
            out += pipe.push(f)
        out += pipe.flush()
        return pipe, out
    runner = TwoPassRunner(lambda: iter(frames), ScriptedDetector({}), lookahead=4, context_scanner=scanner, **kw)
    out = list(runner.frames())
    return runner.pipeline, out


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    TesseractOcr.check()
    frames, gt = make_clip()
    scanner = ContextScanner(TesseractOcr(), ContextConfig(scan_every=3))
    summary = {"frames": N, "scan_every": 3, "ocr": scanner.info()}
    renders = {}
    for name, mode, ov in (("A_live", "live", None), ("B_two_pass", "two_pass", None)):
        pipe, o = render(mode, frames, ContextScanner(TesseractOcr(), ContextConfig(scan_every=3)))
        fr = [x.frame for x in o]
        renders[name] = (pipe, fr)
        summary[name] = {k: dict(zip(("covered_frames", "frames_with_item"), coverage(fr, gt, k))) for k in ("plate", "phone", "sign")}
        summary[name]["context"] = {k: v for k, v in PrivacyReport.build(pipe, "demo").data["context"].items() if k in
                                    ("tracks_by_kind", "tracks_redacted", "tracks_flagged_only", "frames_scanned", "backfilled_regions")}
    pipe, fr = renders["B_two_pass"]
    rep = PrivacyReport.build(pipe, "demo_context.mp4")
    sess = build_session(pipe, rep.data)
    flagged = [m for m in sess.markers if m.exposed]
    summary["review_before"] = {"markers": len(sess.markers), "exposed_needing_decision": len(flagged),
                                "export_allowed": sess.export_gate().allowed, "unviewed": len(sess.export_gate().unviewed_markers)}
    for m in flagged:
        sess.decide(m.id, "escalated")
    pipe_c, o_c = render("two_pass", frames, ContextScanner(TesseractOcr(), ContextConfig(scan_every=3)), sess.overrides())
    fr_c = [x.frame for x in o_c]
    renders["C_after_review"] = (pipe_c, fr_c)
    summary["C_after_review"] = {k: dict(zip(("covered_frames", "frames_with_item"), coverage(fr_c, gt, k))) for k in ("plate", "phone", "sign")}
    sess2 = build_session(pipe_c, PrivacyReport.build(pipe_c, "demo_context.mp4").data, carry=sess.overrides())
    summary["review_after"] = {"markers": len(sess2.markers), "exposed_needing_decision": sum(m.exposed for m in sess2.markers),
                               "carried_floors": len(sess2.overrides().context)}
    meta = encode(fr_c, out / "demo_context.mp4")
    (out / "context_report.json").write_text(PrivacyReport.build(pipe_c, "demo_context.mp4", meta).to_json())
    (out / "context_report.md").write_text(PrivacyReport.build(pipe_c, "demo_context.mp4", meta).to_markdown())
    (out / "review_session.json").write_text(sess.to_json())
    (out / "context_demo_summary.json").write_text(json.dumps(summary, indent=2))
    # preview: original / A live / B two-pass / C after review, at three frames
    pick = [2, 20, 45]
    rows = []
    for label, src in (("original", frames), ("A live", renders["A_live"][1]), ("B two-pass", renders["B_two_pass"][1]), ("C after review", fr_c)):
        row = np.hstack([cv2.resize(src[i], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) for i in pick])
        cv2.putText(row, f"{label}   (frames {pick})", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(row, f"{label}   (frames {pick})", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        rows.append(row)
    cv2.imwrite(str(out / "context_preview.png"), np.vstack(rows))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "runs/demo-context"))
