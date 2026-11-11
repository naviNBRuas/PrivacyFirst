"""Metadata stripping and verification for images and video.

Reports record tag KEYS only, never values, so the report itself cannot leak
GPS coordinates or device serials.
"""
from __future__ import annotations
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Tags that ffmpeg/containers add structurally and that carry no personal data.
BENIGN_TAGS = {"major_brand", "minor_version", "compatible_brands", "handler_name", "vendor_id",
               "language", "duration", "timecode"}


@dataclass
class MetadataResult:
    ok: bool
    keys_before: list[str] = field(default_factory=list)
    keys_after: list[str] = field(default_factory=list)
    has_gps_before: bool = False
    has_gps_after: bool = False
    audio_dropped: bool = True
    notes: list[str] = field(default_factory=list)


def _ffprobe_tags(path: Path) -> tuple[list[str], bool, bool]:
    """Return (tag keys, has_gps_like_tag, has_audio_stream)."""
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found; cannot verify metadata")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags:stream=codec_type",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout or "{}")
    keys: set[str] = set(j.get("format", {}).get("tags", {}) or {})
    audio = False
    for s in j.get("streams", []):
        keys |= set(s.get("tags", {}) or {})
        audio = audio or s.get("codec_type") == "audio"
    low = {k.lower() for k in keys}
    gps = any(("location" in k) or ("gps" in k) or k.startswith("com.apple.quicktime.location") for k in low)
    return sorted(keys), gps, audio


def strip_video(src: Path, dst: Path, keep_audio: bool = False) -> MetadataResult:
    """Re-mux `src` to `dst` with all global/stream metadata removed, then verify.

    Audio is dropped by default (fail closed): voice is an identifier and
    Phase 1 has no voice anonymization.
    """
    import tempfile
    src, dst = Path(src), Path(dst)
    before, gps_before, _ = _ffprobe_tags(src)
    with tempfile.TemporaryDirectory() as td:
        enc = Path(td) / "enc.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map_metadata", "-1", "-map_chapters", "-1",
               "-map", "0:v:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
               "-x264-params", "no-info=1",             # no encoder settings string inside the bitstream
               "-fflags", "+bitexact", "-flags:v", "+bitexact"]
        cmd += (["-map", "0:a?", "-c:a", "aac", "-flags:a", "+bitexact"] if keep_audio else ["-an"])
        subprocess.run(cmd + [str(enc)], check=True)
        # Second pass: stream-copy remux drops the per-stream 'encoder' tag the encoder stamps on itself.
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(enc), "-c", "copy", "-map", "0",
                        "-map_metadata", "-1", "-map_metadata:s:v:0", "-1", "-fflags", "+bitexact",
                        "-movflags", "+faststart", str(dst)], check=True)
    after, gps_after, has_audio = _ffprobe_tags(dst)
    leftover = [k for k in after if k.lower() not in BENIGN_TAGS]
    res = MetadataResult(ok=(not leftover and not gps_after), keys_before=before, keys_after=after,
                         has_gps_before=gps_before, has_gps_after=gps_after, audio_dropped=not has_audio)
    if leftover:
        res.notes.append(f"unexpected metadata keys remain: {leftover}")
    if keep_audio:
        res.notes.append("audio kept: voice is NOT anonymized in Phase 1")
    return res


def strip_image(src: Path, dst: Path) -> MetadataResult:
    """Re-encode pixels into a fresh image so no EXIF/XMP/ICC-embedded extras survive."""
    from PIL import Image
    src, dst = Path(src), Path(dst)
    with Image.open(src) as im:
        exif = im.getexif()
        before = sorted({str(k) for k in exif.keys()} | set(im.info.keys()) - {"dpi"})
        gps = 34853 in exif or "gps" in " ".join(before).lower()      # 34853 = GPSInfo IFD tag
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB") if im.mode not in ("RGB", "L") else im
        clean = Image.frombytes(im.mode, im.size, im.tobytes())
    clean.save(dst)
    with Image.open(dst) as im2:
        after_exif = im2.getexif()
        after = sorted({str(k) for k in after_exif.keys()} | set(im2.info.keys()) - {"dpi"})
        gps_after = 34853 in after_exif
    return MetadataResult(ok=(not after_exif and not gps_after), keys_before=before, keys_after=after,
                          has_gps_before=gps, has_gps_after=gps_after)
