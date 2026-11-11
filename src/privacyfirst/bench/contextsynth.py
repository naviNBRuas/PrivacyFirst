"""Synthetic scenes with ground truth for the context-identifier scan (run 006).

Draws plates, phone numbers, e-mail addresses, street addresses and ordinary signs (NOT identifiers) onto a cluttered
background, then degrades the frame (small text, blur, rotation, noise, low contrast, darkness).

WHAT THIS MEASURES: how the OCR + classification pipeline behaves on clean rendered fonts under controlled
degradation. WHAT IT DOES NOT: real plates (real fonts, embossing, reflections, motion, perspective, dirt), real signage,
real cameras or non-English text. Treat every number as an optimistic upper bound for the same settings on real footage.
All text here is invented; no real plate, number or address is used.
"""
from __future__ import annotations
import glob
import string
from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ..types import Box

_MONO = ["/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]
_SANS = ["/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_SANS_REG = ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

IDENTIFIER_KINDS = {"plate", "phone", "email", "address"}


@dataclass
class Item:
    kind: str                 # plate | phone | email | address | sign
    text: str
    box: Box                  # axis-aligned bounding box in the frame
    identifier: bool
    corners: Optional[np.ndarray] = None   # 4x2 corners of the TEXT itself (possibly rotated); box is the whole patch


@dataclass(frozen=True)
class Variant:
    name: str
    h: int = 28               # cap height of the text in pixels
    rot: float = 0.0          # max |rotation| in degrees
    blur: float = 0.0         # gaussian sigma on the whole frame
    noise: float = 0.0        # gaussian noise sigma
    contrast: float = 1.0     # <1 pulls the frame toward grey
    gamma: float = 1.0        # >1 darkens
    clutter: int = 10         # background rectangles
    distractors: int = 0      # plate-shaped, text-free objects (false-positive bait)


VARIANTS = {v.name: v for v in [
    Variant("clear", h=28),
    Variant("clutter", h=28, clutter=40, distractors=4),
    Variant("small", h=18),
    Variant("tiny", h=12),
    Variant("blur_light", h=28, blur=1.2),
    Variant("blur_heavy", h=28, blur=2.6),
    Variant("rot_10", h=28, rot=10),
    Variant("rot_25", h=28, rot=25),
    Variant("noisy", h=28, noise=18),
    Variant("low_contrast", h=28, contrast=0.35),
    Variant("dark", h=28, gamma=2.4),
    Variant("hard_mix", h=18, rot=10, blur=1.2, noise=10, clutter=30, distractors=3),
]}


def _font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rand_plate(rng) -> str:
    L = lambda n: "".join(rng.choice(list(string.ascii_uppercase), n))
    D = lambda n: "".join(rng.choice(list(string.digits), n))
    style = rng.integers(0, 3)
    if style == 0:
        return f"{L(3)}{D(1)}{L(1)}{D(2)}"          # Mercosul-style
    if style == 1:
        return f"{L(3)}-{D(4)}"                      # older Brazilian-style
    return f"{D(1)}{L(3)}{D(3)}"                     # US-style


def rand_phone(rng) -> str:
    D = lambda n: "".join(rng.choice(list(string.digits), n))
    return [f"({D(2)}) 9{D(4)}-{D(4)}", f"+{D(2)} {D(2)} 9{D(4)}-{D(4)}", f"{D(3)}-{D(3)}-{D(4)}"][int(rng.integers(0, 3))]


def rand_email(rng) -> str:
    a = ["maria", "joao", "ana.lima", "sam.k", "luiza", "pedro.s"]
    d = ["mail.com", "exemplo.com.br", "inbox.org"]
    return f"{a[int(rng.integers(0, len(a)))]}{int(rng.integers(1, 99))}@{d[int(rng.integers(0, len(d)))]}"


def rand_address(rng) -> str:
    s = ["Rua das Flores", "Av. Central", "Elm Street", "Main Road", "Rua Verde"]
    return f"{s[int(rng.integers(0, len(s)))]} {int(rng.integers(1, 999))}"


def rand_sign(rng) -> str:
    return ["SCHOOL ZONE", "KEEP RIGHT", "OPEN", "SALE TODAY", "NO PARKING", "WELCOME"][int(rng.integers(0, 6))]


def _patch(kind: str, text: str, h: int, rng):
    """Returns (BGR patch, (x0, y0, x1, y1) of the text itself inside the patch)."""
    size = max(8, int(round(h / 0.72)))
    if kind == "plate":
        font, bg, fg, pad = _font(_MONO, size), (236, 236, 226), (18, 18, 18), int(h * 0.55)
    elif kind == "sign":
        font, bg, fg, pad = _font(_SANS, size), (30, 110, 60), (245, 245, 245), int(h * 0.5)
    else:
        font, bg, fg, pad = _font(_SANS_REG, size), (245, 245, 240), (25, 25, 25), int(h * 0.4)
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    w, hh = r - l + 2 * pad, b - t + 2 * pad
    im = Image.new("RGB", (w, hh), bg)
    d = ImageDraw.Draw(im)
    d.text((pad - l, pad - t), text, font=font, fill=fg)
    if kind == "plate":
        d.rectangle([0, 0, w - 1, hh - 1], outline=(20, 20, 20), width=max(1, h // 10))
    return np.array(im)[:, :, ::-1].copy(), (pad, pad, pad + (r - l), pad + (b - t))


def _background(W, H, v: Variant, rng) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        img[y, :] = (70 + y // 6, 95 + y // 8, 110 - y // 12)
    for _ in range(v.clutter):
        x, y = int(rng.integers(0, W - 20)), int(rng.integers(0, H - 20))
        w, h = int(rng.integers(10, 90)), int(rng.integers(8, 60))
        col = tuple(int(c) for c in rng.integers(30, 220, 3))
        cv2.rectangle(img, (x, y), (min(W - 1, x + w), min(H - 1, y + h)), col, -1 if rng.random() < 0.6 else 1)
    return img


def _distractor(W, H, rng) -> tuple[np.ndarray, int, int]:
    """Plate-shaped, text-free: a light rectangle with a dark border and a few dashes (not letters)."""
    h = int(rng.integers(18, 34))
    w = int(h * rng.uniform(2.4, 4.4))
    p = np.full((h, w, 3), (225, 225, 215), np.uint8)
    cv2.rectangle(p, (0, 0), (w - 1, h - 1), (20, 20, 20), 2)
    for i in range(int(rng.integers(2, 5))):
        x = 6 + i * (w - 12) // 4
        cv2.line(p, (x, 5), (x, h - 6), (30, 30, 30), 2)
    return p, w, h


def _paste_rot(img, patch, cx, cy, deg, inner=None):
    """Paste a rotated patch; returns (axis-aligned Box, 4x2 corners of `inner` (x0,y0,x1,y1 in patch coords) or of the patch)."""
    h, w = patch.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    rot = cv2.warpAffine(patch, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), M, (nw, nh), flags=cv2.INTER_LINEAR)
    H, W = img.shape[:2]
    x1, y1 = int(cx - nw / 2), int(cy - nh / 2)
    x1, y1 = max(0, min(W - nw, x1)), max(0, min(H - nh, y1))
    roi = img[y1:y1 + nh, x1:x1 + nw]
    m = (mask > 127)[:, :, None]
    roi[:] = np.where(m, rot, roi)
    x0, y0, xe, ye = inner if inner else (0, 0, w, h)
    corners = cv2.transform(np.array([[[x0, y0], [xe, y0], [xe, ye], [x0, ye]]], np.float32), M)[0] + np.array([x1, y1], np.float32)
    return Box(x1, y1, x1 + nw, y1 + nh), corners


def _overlaps(b: Box, others: list[Box], pad: int = 6) -> bool:
    return any(not (b.x2 + pad < o.x1 or o.x2 + pad < b.x1 or b.y2 + pad < o.y1 or o.y2 + pad < b.y1) for o in others)


def make_scene(seed: int, v: Variant, size=(800, 560), kinds=("plate", "phone", "email", "address", "sign")):
    """Returns (frame BGR uint8, [Item]). One item per kind; items never overlap each other or a distractor
    (rejection sampling), so ground truth is never partly covered. An item that cannot be placed is skipped."""
    rng = np.random.default_rng(seed)
    W, H = size
    img = _background(W, H, v, rng)
    gens = {"plate": rand_plate, "phone": rand_phone, "email": rand_email, "address": rand_address, "sign": rand_sign}
    taken: list[Box] = []
    for _ in range(v.distractors):          # distractors first so they can never cover a ground-truth item
        p, _, _ = _distractor(W, H, rng)
        taken.append(_paste_rot(img, p, float(rng.uniform(60, W - 60)), float(rng.uniform(30, H - 30)), float(rng.uniform(-8, 8)))[0])
    items: list[Item] = []
    for k in kinds:
        text = gens[k](rng)
        deg = float(rng.uniform(-v.rot, v.rot)) if v.rot else 0.0
        patch, inner = _patch(k, text, v.h, rng)
        for _try in range(60):
            cx, cy = float(rng.uniform(0.1 * W, 0.9 * W)), float(rng.uniform(0.08 * H, 0.92 * H))
            ph, pw = patch.shape[:2]
            M = cv2.getRotationMatrix2D((pw / 2, ph / 2), deg, 1.0)
            nw, nh = int(ph * abs(M[0, 1]) + pw * abs(M[0, 0])), int(ph * abs(M[0, 0]) + pw * abs(M[0, 1]))
            x1, y1 = max(0, min(W - nw, int(cx - nw / 2))), max(0, min(H - nh, int(cy - nh / 2)))
            cand = Box(x1, y1, x1 + nw, y1 + nh)
            if not _overlaps(cand, taken):
                box, corners = _paste_rot(img, patch, cx, cy, deg, inner)
                taken.append(box)
                items.append(Item(k, text, box, k in IDENTIFIER_KINDS, corners))
                break
    f = img.astype(np.float32)
    if v.contrast != 1.0:
        f = 128 + (f - 128) * v.contrast
    if v.gamma != 1.0:
        f = 255 * np.clip(f / 255, 0, 1) ** v.gamma
    out = np.clip(f, 0, 255).astype(np.uint8)
    if v.blur:
        out = cv2.GaussianBlur(out, (0, 0), v.blur)
    if v.noise:
        out = np.clip(out.astype(np.float32) + rng.normal(0, v.noise, out.shape), 0, 255).astype(np.uint8)
    return out, items


def item_mask(item: Item, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask of the text itself (rotated), so coverage is judged on the characters, not on blank plate border."""
    m = np.zeros(shape, np.uint8)
    if item.corners is not None:
        cv2.fillPoly(m, [item.corners.astype(np.int32)], 1)
    else:
        b = item.box
        m[int(b.y1):int(b.y2), int(b.x1):int(b.x2)] = 1
    return m.astype(bool)
