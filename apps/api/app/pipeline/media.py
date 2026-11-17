import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.pipeline.ffmpeg_cmd import (
    cut_audio_command,
    download_command,
    energy_command,
    extract_audio_command,
    probe_duration_command,
    render_command,
)
from app.pipeline.subtitles import build_ass
from app.pipeline.words import Word, words_between

logger = logging.getLogger("clip.media")


class MediaError(RuntimeError):
    pass


def run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "comando falhou").strip()
        raise MediaError(detail[-800:])
    return (completed.stdout or "").strip()


def probe_duration(path: Path) -> float:
    raw = run_command(probe_duration_command(path))
    try:
        return float(raw)
    except ValueError as exc:
        raise MediaError("Não foi possível ler a duração do vídeo") from exc


def download_url(url: str, destination: Path, max_bytes: int) -> None:
    run_command(download_command(url, destination, max_bytes))
    if not destination.exists():
        matches = list(destination.parent.glob(destination.stem + "*"))
        if len(matches) == 1:
            matches[0].replace(destination)
    if not destination.exists():
        raise MediaError("O download não gerou o arquivo de vídeo")


def extract_audio(source: Path, destination: Path) -> None:
    run_command(extract_audio_command(source, destination))


def cut_audio(source: Path, destination: Path, start: float, end: float) -> None:
    run_command(cut_audio_command(source, destination, start, end))


def audio_energy(path: Path, window_seconds: float = 1.0) -> list[tuple[float, float]]:
    completed = subprocess.run(energy_command(path), capture_output=True, check=False)
    if completed.returncode != 0:
        return []
    samples = completed.stdout
    if len(samples) < 4:
        return []
    import array

    values = array.array("h")
    usable = len(samples) - (len(samples) % 2)
    values.frombytes(samples[:usable])
    per_window = max(1, int(8000 * window_seconds))
    peaks: list[tuple[float, float]] = []
    for index in range(0, len(values), per_window):
        chunk = values[index : index + per_window]
        if not chunk:
            continue
        mean_square = sum(sample * sample for sample in chunk) / len(chunk)
        level = (mean_square**0.5) / 32768
        peaks.append((index / 8000, level))
    return peaks


def render_clip(
    source: Path,
    destination: Path,
    *,
    start: float,
    end: float,
    words: list[Word],
    caption_text: str,
    font_name: str,
    font_size: int,
    primary_color: str,
    highlight_color: str,
    position: str,
    frame: tuple[float, float, float, float] | None = None,
    hook: str = "",
) -> None:
    selected = words_between(words, start, end)
    relative = [Word(word.word, max(0.0, word.start - start), max(0.0, word.end - start)) for word in selected]
    timed = _match_caption(relative, caption_text, end - start)
    with tempfile.TemporaryDirectory(prefix="clip-ass-") as directory:
        subtitles = Path(directory) / "captions.ass"
        subtitles.write_text(
            build_ass(
                timed,
                font_name=font_name,
                font_size=font_size,
                primary_color=primary_color,
                highlight_color=highlight_color,
                position=position,
                hook=hook,
                duration=max(0.0, end - start),
            ),
            encoding="utf-8",
        )
        run_command(render_command(source, destination, subtitles, start, end, frame))


def cleanup_temp(max_age_seconds: int) -> int:
    import time

    root = Path("/tmp")
    removed = 0
    now = time.time()
    if not root.exists():
        return 0
    for path in root.glob("clip-*"):
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < max_age_seconds:
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed += 1
    return removed


def make_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="clip-", dir="/tmp"))


def _match_caption(words: list[Word], caption_text: str, duration: float) -> list[Word]:
    original = " ".join(word.word.strip() for word in words).strip()
    edited = " ".join(caption_text.split()).strip()
    if words and edited == original:
        return words
    tokens = edited.split()
    if not tokens or duration <= 0:
        return words
    step = duration / len(tokens)
    return [Word(token, index * step, (index + 1) * step) for index, token in enumerate(tokens)]


def require_limits(path: Path, duration: float, settings: Settings) -> None:
    size = path.stat().st_size
    if size > settings.max_upload_bytes:
        raise MediaError("O arquivo passa do tamanho máximo configurado")
    if duration > settings.max_video_duration_seconds:
        raise MediaError("O vídeo passa da duração máxima configurada")
