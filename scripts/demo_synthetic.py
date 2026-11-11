"""Synthetic end-to-end demo. No real people, no models, no downloads.

Two drawn faces move through a scene. A scripted detector simulates the failure
modes the pipeline exists for: a 8-frame dropout on face A and a late first
detection on face B that is recovered by lookahead backfill. NOTE: a face first detected
MORE than `lookahead` frames late would already have been emitted; see docs/KNOWN_LIMITATIONS.md. Writes preview PNG/GIF, redacted MP4, and report.
Usage: python scripts/demo_synthetic.py OUT_DIR
"""
import math, sys, tempfile
from pathlib import Path
import cv2, numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from privacyfirst.detect import ScriptedDetector
from privacyfirst.metadata import strip_video
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.policy import PolicyConfig
from privacyfirst.report import PrivacyReport
from privacyfirst.types import Box, Detection

W, H, N, FPS = 320, 240, 48, 12


def face_box(t, who):
    if who == "A":
        cx, cy, s = 60 + t * 4.5, 120 + 25 * math.sin(t / 5), 34
    else:
        cx, cy, s = 270 - t * 3.2, 90 + 15 * math.cos(t / 4), 28
    return Box(cx - s, cy - s * 1.2, cx + s, cy + s * 1.2)


def draw_scene(t):
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        img[y, :] = (60 + y // 4, 90 + y // 6, 110)          # BGR gradient
    for who, skin in (("A", (150, 180, 230)), ("B", (120, 150, 200))):
        b = face_box(t, who)
        cx, cy = (int(v) for v in b.center)
        rx, ry = int(b.w / 2), int(b.h / 2)
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, skin, -1)
        for dx in (-rx // 2, rx // 2):
            cv2.circle(img, (cx + dx, cy - ry // 4), max(2, rx // 6), (40, 30, 30), -1)
        cv2.ellipse(img, (cx, cy + ry // 2), (rx // 2, ry // 6), 0, 0, 180, (60, 40, 120), 2)
    return img


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    script = {}
    for t in range(N):
        dets = []
        if not (20 <= t < 28):                                # A: 8-frame detector dropout
            dets.append(Detection(face_box(t, "A"), 0.92))
        if t >= 3:                                            # B: first detected 3 frames late (inside the 4-frame lookahead, so backfill covers it)
            dets.append(Detection(face_box(t, "B"), 0.35 if 30 <= t < 34 else 0.88))   # brief low confidence
        script[t] = dets
    det = ScriptedDetector(script)
    verif = ScriptedDetector({})                              # demo verifier sees nothing residual
    pipe = RedactionPipeline(det, PolicyConfig.standard(), lookahead=4, verifier=verif)
    raws, outs = [], []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "r.mp4"
        vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        for t in range(N):
            f = draw_scene(t); raws.append(f)
            for o in pipe.push(f):
                outs.append(o); vw.write(o.frame)
        for o in pipe.flush():
            outs.append(o); vw.write(o.frame)
        vw.release()
        meta = strip_video(tmp, out / "demo_redacted.mp4")
    rep = PrivacyReport.build(pipe, "synthetic_demo (drawn faces, no real people)", meta)
    (out / "report.json").write_text(rep.to_json()); (out / "report.md").write_text(rep.to_markdown())

    picks = [0, 8, 12, 19, 23, 27, 32, 44]
    cell_w = 200; cell_h = int(H * cell_w / W)
    def cell(img, label):
        c = cv2.resize(img, (cell_w, cell_h)).copy()
        cv2.rectangle(c, (0, 0), (cell_w, 14), (0, 0, 0), -1)
        cv2.putText(c, label, (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
        return c
    def tag(o):
        parts = [f"{k}:{v}" for k, v in sorted(o.treatments.items())]
        return f"f{o.idx} " + " ".join(parts)
    top = np.hstack([cell(raws[i], f"RAW f{i} (demo only)") for i in picks])
    bot = np.hstack([cell(outs[i].frame, tag(outs[i])) for i in picks])
    sheet = np.vstack([top, bot])
    cv2.imwrite(str(out / "preview.png"), sheet)
    frames = [Image.fromarray(cv2.cvtColor(np.hstack([cv2.resize(raws[i], (W, H)), outs[i].frame]), cv2.COLOR_BGR2RGB))
              for i in range(0, N, 2)]
    frames[0].save(out / "preview.gif", save_all=True, append_images=frames[1:], duration=160, loop=0)
    print(rep.to_markdown())


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "runs/run-001"))
