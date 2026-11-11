import subprocess
import pytest
from PIL import Image
from privacyfirst.metadata import strip_image, strip_video, _ffprobe_tags


def test_video_metadata_and_gps_stripped(tmp_path):
    src = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
                    "-metadata", "title=Birthday", "-metadata", "location=+52.5200+013.4050/",
                    "-metadata", "com.apple.quicktime.model=iPhone", str(src)], check=True)
    keys, gps, audio = _ffprobe_tags(src)
    assert gps and audio
    dst = tmp_path / "out.mp4"
    res = strip_video(src, dst)
    assert res.ok and not res.has_gps_after and res.audio_dropped
    assert "location" in res.keys_before and "location" not in res.keys_after
    assert "title" not in res.keys_after


def test_image_exif_gps_stripped(tmp_path):
    src = tmp_path / "a.jpg"
    im = Image.new("RGB", (32, 32), (200, 10, 10))
    ex = im.getexif()
    ex[271] = "AcmeCam"                     # Make
    ex[306] = "2026:01:01 10:00:00"         # DateTime
    gps = ex.get_ifd(34853)
    gps[1], gps[2] = "N", (52.0, 31.0, 12.0)
    im.save(src, exif=ex)
    res = strip_image(src, tmp_path / "b.jpg")
    assert res.has_gps_before and res.ok and not res.has_gps_after
    assert not Image.open(tmp_path / "b.jpg").getexif()
