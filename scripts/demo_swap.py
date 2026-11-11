"""Face-change path demo with the STUB (cartoon) replacer. Shows the gates, not an AI face change.

Story on synthetic drawn faces (no real people):
  * Both faces are mosaic for the first frames (track not yet stable), then swap to a stable synthetic identity.
  * Face A: detector drops out (frames 20-27) -> mosaic with sticky hysteresis, then recovers to the SAME identity.
  * Face B: a scripted recognizer failure at ~frame 44 -> permanent mosaic, applied to already-buffered frames too.
Usage: python scripts/demo_swap.py OUT_DIR
"""
import sys
import tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import math
import demo_synthetic as ds
from demo_synthetic import H, W, draw_scene
from privacyfirst.types import Box


def face_box(t, who):
    """Demo-specific in-frame trajectories (the run-001 demo drifts off-frame beyond ~50 frames)."""
    if who == "A":
        cx, cy, s = 100 + 40 * math.sin(t / 13), 125 + 20 * math.sin(t / 7), 34
    else:
        cx, cy, s = 225 - 35 * math.sin(t / 10 + 1), 95 + 15 * math.cos(t / 6), 28
    return Box(cx - s, cy - s * 1.2, cx + s, cy + s * 1.2)


ds.face_box = face_box                       # draw_scene() looks this up in its own module
from privacyfirst.detect import ScriptedDetector
from privacyfirst.identity import IdentityAssigner, generate_stub_library
from privacyfirst.metadata import strip_video
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.policy import PolicyConfig
from privacyfirst.replace import StubReplacer
from privacyfirst.report import PrivacyReport
from privacyfirst.swapgate import FunctionRecognizer, SwapVerifier
from privacyfirst.types import Detection

N, FPS = 72, 12


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    script = {t: ([] if 20 <= t < 28 else [Detection(face_box(t, "A"), 0.92)]) + [Detection(face_box(t, "B"), 0.9)]
              for t in range(N)}
    hint = {"t": 0}
    def rec_a(orig, cand):                      # demo-only scripted failure: face B's (narrower) head crop fails from frame 44
        return 0.9 if (hint["t"] >= 44 and orig.shape[1] < 110) else 0.1
    sv = SwapVerifier([FunctionRecognizer("recognizer-A (scripted)", rec_a),
                       FunctionRecognizer("recognizer-B (scripted)", lambda a, b: 0.1)])
    ids = IdentityAssigner(generate_stub_library(0, per_cell=6), seed=11, allow_unvetted=True)
    pipe = RedactionPipeline(ScriptedDetector(script), PolicyConfig(swap_enabled=True), lookahead=4,
                             replacer=StubReplacer(), identities=ids, swap_verifier=sv)
    raws, outs = [], []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "r.mp4"
        vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        for t in range(N):
            f = draw_scene(t); raws.append(f); hint["t"] = t
            for o in pipe.push(f):
                outs.append(o); vw.write(o.frame)
        for o in pipe.flush():
            outs.append(o); vw.write(o.frame)
        vw.release()
        meta = strip_video(tmp, out / "demo_swap.mp4")
    rep = PrivacyReport.build(pipe, "swap demo (drawn faces, STUB replacer)", meta)
    (out / "swap_report.json").write_text(rep.to_json()); (out / "swap_report.md").write_text(rep.to_markdown())

    picks = [2, 8, 16, 24, 36, 46, 60, 70]
    cw = 200; ch = int(H * cw / W)
    def cell(img, label, color=(255, 255, 255)):
        c = cv2.resize(img, (cw, ch)).copy()
        cv2.rectangle(c, (0, 0), (cw, 14), (0, 0, 0), -1)
        cv2.putText(c, label, (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)
        return c
    tag = lambda o: f"f{o.idx} " + " ".join(f"{k}:{v}" for k, v in sorted(o.treatments.items()))
    top = np.hstack([cell(raws[i], f"RAW f{i} (demo only)") for i in picks])
    bot = np.hstack([cell(outs[i].frame, tag(outs[i])) for i in picks])
    banner = np.zeros((18, top.shape[1], 3), np.uint8)
    cv2.putText(banner, "STUB generator (cartoon faces) - shows the swap GATES, stable identity and fallbacks; NOT an AI face change",
                (6, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (80, 200, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out / "swap_preview.png"), np.vstack([banner, top, bot]))
    frames = [Image.fromarray(cv2.cvtColor(np.hstack([raws[i], outs[i].frame]), cv2.COLOR_BGR2RGB)) for i in range(0, N, 2)]
    frames[0].save(out / "swap_preview.gif", save_all=True, append_images=frames[1:], duration=170, loop=0)
    print(rep.to_markdown())


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "runs/run-003"))
