"""Live vs two-pass demo on synthetic drawn faces (no real people, no models, STUB replacer).

Same scripted detector, same policy (face change enabled with the non-AI stub), two ways of processing the clip:
  * Face A is visible from frame 0 but the detector only finds it at frame 14 (turned away / blur). That is later than the
    4-frame lookahead, so LIVE mode has already emitted frames 0-9 with the face untouched. TWO-PASS covers them.
  * Face B is detected, then lost for 35 frames (longer than the ghost-track life of 30), then found again. LIVE mode ends
    the ghost after 30 frames (one uncovered frame at f61) and starts a second track for the same person. TWO-PASS stitches
    the fragments into one person and covers the whole outage from both sides. (In this particular demo the deterministic
    identity assigner happens to hand the live run's second track the same stub identity; the benchmark, not this demo,
    measures identity changes.)
Usage: python scripts/demo_two_pass.py OUT_DIR
"""
import json
import math
import sys
import tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from privacyfirst.detect import ScriptedDetector
from privacyfirst.identity import IdentityAssigner, generate_stub_library
from privacyfirst.metadata import strip_video
from privacyfirst.offline import TwoPassRunner
from privacyfirst.pipeline import RedactionPipeline
from privacyfirst.policy import PolicyConfig
from privacyfirst.replace import StubReplacer
from privacyfirst.report import PrivacyReport
from privacyfirst.swapgate import FunctionRecognizer, SwapVerifier
from privacyfirst.types import Box, Detection

W, H, N, FPS = 320, 240, 84, 12
A_FIRST_SEEN, B_LOST = 14, range(31, 66)


def face_box(t, who):
    if who == "A":
        cx, cy, s = 95 + 38 * math.sin(t / 15), 130 + 18 * math.sin(t / 8), 34
    else:
        cx, cy, s = 232 - 28 * math.sin(t / 19 + 1), 100 + 14 * math.cos(t / 9), 27
    return Box(cx - s, cy - s * 1.2, cx + s, cy + s * 1.2)


def draw_scene(t):
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        img[y, :] = (60 + y // 4, 90 + y // 6, 110)
    for who, skin in (("A", (150, 180, 230)), ("B", (120, 150, 200))):
        b = face_box(t, who)
        cx, cy = (int(v) for v in b.center)
        rx, ry = int(b.w / 2), int(b.h / 2)
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, skin, -1)
        for dx in (-rx // 2, rx // 2):
            cv2.circle(img, (cx + dx, cy - ry // 4), max(2, rx // 6), (40, 30, 30), -1)
        cv2.ellipse(img, (cx, cy + ry // 2), (rx // 2, ry // 6), 0, 0, 180, (60, 40, 120), 2)
    return img


def script():
    s = {}
    for t in range(N):
        d = []
        if t >= A_FIRST_SEEN:
            d.append(Detection(face_box(t, "A"), 0.9))
        if t not in B_LOST:
            d.append(Detection(face_box(t, "B"), 0.9))
        s[t] = d
    return s


def make_parts():
    sv = SwapVerifier([FunctionRecognizer("recognizer-A (sim)", lambda a, b: 0.1),
                       FunctionRecognizer("recognizer-B (sim)", lambda a, b: 0.1)])
    ids = IdentityAssigner(generate_stub_library(0, per_cell=6), seed=11, allow_unvetted=True)
    return dict(replacer=StubReplacer(), identities=ids, swap_verifier=sv)


def unchanged_frac(out, raw, box):
    x1, y1, x2, y2 = box.clamp_int(W, H)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return float((out[y1:y2, x1:x2] == raw[y1:y2, x1:x2]).all(axis=2).mean())


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    raws = [draw_scene(t) for t in range(N)]
    cfg = PolicyConfig(swap_enabled=True)

    live = RedactionPipeline(ScriptedDetector(script()), cfg, lookahead=4, **make_parts())
    live_outs = []
    for f in raws:
        live_outs += live.push(f)
    live_outs += live.flush()

    runner = TwoPassRunner(lambda: iter(raws), ScriptedDetector(script()), cfg, lookahead=4, **make_parts())
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "r.mp4"
        vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        tp_outs = []
        for o in runner.frames():
            tp_outs.append(o)
            vw.write(o.frame)
        vw.release()
        meta = strip_video(tmp, out / "demo_two_pass.mp4")
    rep = PrivacyReport.build(runner.pipeline, "two-pass demo (drawn faces, STUB replacer)", meta)
    (out / "two_pass_report.json").write_text(rep.to_json())
    (out / "two_pass_report.md").write_text(rep.to_markdown())

    # ---- measurements (leak = face region left >=90% pixel-identical to the raw frame)
    def leaks(outs, who, frames):
        return [t for t in frames if unchanged_frac(outs[t].frame, raws[t], face_box(t, who)) >= 0.9]
    a_frames = range(N)
    b_frames = range(N)
    meas = {
        "face_A_visible_all_frames_detected_from": A_FIRST_SEEN,
        "face_A_leaked_frames_live": leaks(live_outs, "A", a_frames),
        "face_A_leaked_frames_two_pass": leaks(tp_outs, "A", a_frames),
        "face_B_leaked_frames_live": leaks(live_outs, "B", b_frames),
        "face_B_leaked_frames_two_pass": leaks(tp_outs, "B", b_frames),
        "identities_by_track_live": {str(tid): {"frames": [t["first_frame"], t["last_frame"]], "identity": t["identity_id"]}
                                     for tid, t in sorted(live.stats.tracks.items())},
        "identities_by_person_two_pass": {str(tid): {"frames": [t["first_frame"], t["last_frame"]], "identity": t["identity_id"]}
                                          for tid, t in sorted(runner.pipeline.stats.tracks.items())},
        "live_tracks": len(live.stats.tracks), "two_pass_people": runner.plan.summary["persons"],
        "two_pass_plan": runner.plan.summary,
    }
    (out / "two_pass_demo_summary.json").write_text(json.dumps(meas, indent=2))

    picks = [3, 8, 13, 30, 48, 62, 70, 80]
    cw = 200
    ch = int(H * cw / W)
    def cell(img, label, color=(255, 255, 255)):
        c = cv2.resize(img, (cw, ch)).copy()
        cv2.rectangle(c, (0, 0), (cw, 14), (0, 0, 0), -1)
        cv2.putText(c, label, (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)
        return c
    tag = lambda o: f"f{o.idx} " + " ".join(f"{k}:{v}" for k, v in sorted(o.treatments.items()))
    leak_a_live = set(meas["face_A_leaked_frames_live"])
    rows = [np.hstack([cell(raws[i], f"RAW f{i} (demo only)") for i in picks]),
            np.hstack([cell(live_outs[i].frame, "LIVE " + tag(live_outs[i]), (80, 80, 255) if i in leak_a_live else (255, 255, 255)) for i in picks]),
            np.hstack([cell(tp_outs[i].frame, "2PASS " + tag(tp_outs[i]), (120, 255, 120)) for i in picks])]
    banner = np.zeros((18, rows[0].shape[1], 3), np.uint8)
    cv2.putText(banner, "Face A first detected at f14 (red = LIVE left it unredacted).  Face B lost f31-65: live = 2 tracks + 1 uncovered frame (f61); two-pass = 1 person.  STUB faces.",
                (6, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 200, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out / "two_pass_preview.png"), np.vstack([banner] + rows))
    gif = [Image.fromarray(cv2.cvtColor(np.hstack([raws[i], live_outs[i].frame, tp_outs[i].frame]), cv2.COLOR_BGR2RGB)) for i in range(0, N, 2)]
    gif[0].save(out / "two_pass_preview.gif", save_all=True, append_images=gif[1:], duration=170, loop=0)
    print(json.dumps({k: v for k, v in meas.items() if k != "two_pass_plan"}, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "runs/run-004"))
