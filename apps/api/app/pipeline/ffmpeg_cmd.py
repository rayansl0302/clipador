from pathlib import Path


def probe_duration_command(path: Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]


def extract_audio_command(source: Path, destination: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        str(destination),
    ]


def cut_audio_command(source: Path, destination: Path, start: float, end: float) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        str(destination),
    ]


def energy_command(source: Path) -> list[str]:
    return ["ffmpeg", "-v", "error", "-i", str(source), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render_command(
    source: Path,
    destination: Path,
    subtitles: Path,
    start: float,
    end: float,
    frame: tuple[float, float, float, float] | None = None,
) -> list[str]:
    if frame is None:
        face = "scale=1080:1312:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1312,setsar=1"
    else:
        x, y, w, h = frame
        face = (
            f"crop=iw*{w:.6f}:ih*{h:.6f}:iw*{x:.6f}:ih*{y:.6f},"
            "scale=1080:1312:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1312,setsar=1"
        )
    content = "scale=1080:608:force_original_aspect_ratio=decrease:flags=lanczos,pad=1080:608:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    video_filter = (
        "[0:v]split=2[face_src][content_src];"
        f"[face_src]{face}[face];"
        f"[content_src]{content}[content];"
        f"[face][content]vstack=inputs=2,subtitles={escape_filter_path(subtitles)}"
    )
    return [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-filter_complex",
        video_filter,
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(destination),
    ]


def download_command(url: str, destination: Path, max_bytes: int) -> list[str]:
    return [
        "yt-dlp",
        "--no-playlist",
        "--no-progress",
        "-f",
        "bv*[protocol=https]+ba[protocol=https]/bv*+ba/b",
        "-S",
        "res,tbr",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        str(max_bytes),
        "-o",
        str(destination),
        url,
    ]
