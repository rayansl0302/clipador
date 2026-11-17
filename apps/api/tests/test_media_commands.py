from pathlib import Path

from app.pipeline.ffmpeg_cmd import escape_filter_path, extract_audio_command, render_command
from app.pipeline.subtitles import build_ass
from app.pipeline.words import Word


def test_ass_highlights_current_word() -> None:
    words = [Word("Olha", 0.0, 0.4), Word("isso", 0.4, 0.9)]
    ass = build_ass(
        words,
        font_name="DejaVu Sans",
        font_size=72,
        primary_color="#FFFFFF",
        highlight_color="#FFE14A",
        position="bottom",
    )
    assert "\\c&H004AE1FF&" in ass
    assert "\\fscx112" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:00.40" in ass
    assert "Olha" in ass
    assert "PlayResX: 1080" in ass
    assert ",2," in ass.split("Style: Default,", 1)[1].split("\n", 1)[0]


def test_render_command_is_vertical_with_loudnorm() -> None:
    command = render_command(Path("/tmp/in.mp4"), Path("/tmp/out.mp4"), Path("/tmp/captions.ass"), 12.5, 40)
    joined = " ".join(command)
    assert "vstack=inputs=2" in joined
    assert "scale=1080:1312:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1312" in joined
    assert "pad=1080:608:(ow-iw)/2:(oh-ih)/2:black" in joined
    assert "-crf" in command and command[command.index("-crf") + 1] == "18"
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in joined
    assert "subtitles=" in joined
    assert command[0] == "ffmpeg"
    assert "-ss" in command and "12.500" in command


def test_extract_audio_is_mono_16khz() -> None:
    command = extract_audio_command(Path("/tmp/in.mp4"), Path("/tmp/out.flac"))
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert "flac" in command


def test_escape_filter_path() -> None:
    escaped = escape_filter_path(Path("/tmp/clip:1/captions.ass"))
    assert "\\:" in escaped
