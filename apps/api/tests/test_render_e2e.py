import shutil
import subprocess
from pathlib import Path

import pytest

from app.pipeline.ffmpeg_cmd import extract_audio_command, render_command
from app.pipeline.media import run_command
from app.pipeline.subtitles import build_ass
from app.pipeline.words import Word


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg ausente")
def test_render_short_clip(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    audio = tmp_path / "audio.flac"
    output = tmp_path / "out.mp4"
    subtitles = tmp_path / "captions.ass"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    run_command(extract_audio_command(source, audio))
    assert audio.stat().st_size > 0
    subtitles.write_text(
        build_ass([Word("Oi", 0.2, 0.8), Word("corte", 0.8, 1.4)], font_name="DejaVu Sans", font_size=48, primary_color="#FFFFFF", highlight_color="#FFE14A", position="bottom"),
        encoding="utf-8",
    )
    run_command(render_command(source, output, subtitles, 0, 2))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "1080,1920"
