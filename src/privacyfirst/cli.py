"""CLI: privacyfirst video IN OUT [--mode two-pass|live] [--report-json R] [--report-md R] | privacyfirst image IN OUT

Recorded files default to TWO-PASS mode (whole-file analysis, then render): it closes the live-mode leak where a face
first detected after the lookahead leaves earlier frames unredacted. Pass 1 keeps boxes only, never pixels."""
from __future__ import annotations
import argparse
import sys
import tempfile
from pathlib import Path
import cv2
from .context import ContextConfig, ContextScanner, LiveContext, OcrUnavailable, TesseractOcr
from .metadata import strip_image, strip_video
from .detectors import make_detector
from .offline import PlanMismatchError, TwoPassRunner
from .pipeline import RedactionPipeline
from .policy import PolicyConfig
from .report import PrivacyReport
from .review import build_session


def _read_frames(src: Path):
    cap = cv2.VideoCapture(str(src))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def _make_scanner(a: argparse.Namespace, every: int | None = None):
    """None when the scan is off. Raises OcrUnavailable BEFORE any output is produced (no silent fallback to 'no scan')."""
    if not a.context_scan:
        return None
    TesseractOcr.check(a.ocr_lang)
    cfg = ContextConfig() if every is None and a.context_every is None else ContextConfig(scan_every=every or a.context_every)
    return ContextScanner(TesseractOcr(lang=a.ocr_lang), cfg)


def _write_review(a: argparse.Namespace, pipe, rep) -> None:
    if getattr(a, "review_json", None):
        Path(a.review_json).write_text(build_session(pipe, rep.data).to_json())


def _run_video(a: argparse.Namespace) -> int:
    src, dst = Path(a.input), Path(a.output)
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        print(f"cannot open {src}", file=sys.stderr)
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    try:
        det = make_detector(a.detector, a.model_dir)
    except (FileNotFoundError, ImportError, ValueError) as e:     # no weights: say so, never fall back silently to Haar
        print(f"detector unavailable: {e}", file=sys.stderr)
        return 2
    try:
        scanner = _make_scanner(a)
    except OcrUnavailable as e:
        print(f"context scan unavailable: {e}", file=sys.stderr)
        return 2
    policy = PolicyConfig.standard() if a.profile == "standard" else PolicyConfig.strict()
    verifier = det if a.verify else None
    with tempfile.TemporaryDirectory() as td:       # intermediate holds REDACTED frames only
        tmp = Path(td) / "redacted.mp4"
        vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        try:
            if a.mode == "two-pass":
                runner = TwoPassRunner(lambda: _read_frames(src), det, policy, lookahead=a.lookahead, verifier=verifier,
                                       context_scanner=scanner)
                for o in runner.frames():
                    vw.write(o.frame)
                pipe = runner.pipeline
            else:
                pipe = RedactionPipeline(det, policy, lookahead=a.lookahead, verifier=verifier,
                                         context=LiveContext(scanner) if scanner else None)
                for frame in _read_frames(src):
                    for o in pipe.push(frame):
                        vw.write(o.frame)
                for o in pipe.flush():
                    vw.write(o.frame)
        except (PlanMismatchError, ValueError) as e:      # fail closed: no output file is produced
            vw.release()
            print(f"aborted, no output written: {e}", file=sys.stderr)
            return 3
        vw.release()
        meta = strip_video(tmp, dst, keep_audio=False)   # source audio never copied in Phase 1
    rep = PrivacyReport.build(pipe, src.name, meta)
    if a.report_json:
        Path(a.report_json).write_text(rep.to_json())
    if a.report_md:
        Path(a.report_md).write_text(rep.to_markdown())
    _write_review(a, pipe, rep)
    print(rep.to_markdown())
    return 0 if meta.ok else 1


def _run_image(a: argparse.Namespace) -> int:
    img = cv2.imread(a.input)
    if img is None:
        print(f"cannot open {a.input}", file=sys.stderr)
        return 2
    try:
        det = make_detector(a.detector, a.model_dir)
    except (FileNotFoundError, ImportError, ValueError) as e:
        print(f"detector unavailable: {e}", file=sys.stderr)
        return 2
    try:
        scanner = _make_scanner(a, every=1)
    except OcrUnavailable as e:
        print(f"context scan unavailable: {e}", file=sys.stderr)
        return 2
    pipe = RedactionPipeline(det, lookahead=1, verifier=det if a.verify else None, context=LiveContext(scanner) if scanner else None)
    out = pipe.push(img) + pipe.flush()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "r.png"
        cv2.imwrite(str(tmp), out[0].frame)
        meta = strip_image(tmp, Path(a.output))
    rep = PrivacyReport.build(pipe, Path(a.input).name, meta)
    _write_review(a, pipe, rep)
    print(rep.to_markdown())
    return 0 if meta.ok else 1


def _context_args(sp) -> None:
    sp.add_argument("--context-scan", action="store_true",
                    help="scan for plates, phone numbers, e-mails, addresses and readable text with OCR (needs tesseract; heuristic, off by default)")
    sp.add_argument("--context-every", type=int, default=None, help="scan every Nth frame (default 3; 1 = every frame, slowest, safest)")
    sp.add_argument("--ocr-lang", default="eng", help="tesseract language(s), e.g. eng or eng+por (must be installed)")
    sp.add_argument("--review-json", help="write the pre-publish review session (markers, cards, export gate) as JSON")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="privacyfirst", description="Local-first fail-closed face redaction (Phase 1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("video"); v.add_argument("input"); v.add_argument("output")
    v.add_argument("--profile", choices=["strict", "standard"], default="strict")
    v.add_argument("--mode", choices=["two-pass", "live"], default="two-pass",
                   help="two-pass (default for recorded files) or live (streaming, bounded lookahead)")
    v.add_argument("--detector", choices=["haar", "yunet", "mediapipe"], default="haar",
                   help="haar = placeholder (default); yunet/mediapipe need model files, see docs/phase0/MODEL_SETUP.md")
    v.add_argument("--model-dir", help="directory with model files (or set PRIVACYFIRST_MODEL_DIR)")
    v.add_argument("--lookahead", type=int, default=4)
    v.add_argument("--no-verify", dest="verify", action="store_false")
    v.add_argument("--report-json"); v.add_argument("--report-md")
    _context_args(v)
    v.set_defaults(fn=_run_video)
    i = sub.add_parser("image"); i.add_argument("input"); i.add_argument("output")
    i.add_argument("--no-verify", dest="verify", action="store_false")
    i.add_argument("--detector", choices=["haar", "yunet", "mediapipe"], default="haar")
    i.add_argument("--model-dir")
    _context_args(i)
    i.set_defaults(fn=_run_image)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
