import json
import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.pipeline.words import Word

logger = logging.getLogger("clip.transcribe")


class TranscribeError(RuntimeError):
    pass


def transcribe_file(path: Path, settings: Settings, offset: float = 0.0) -> tuple[list[Word], str]:
    provider = settings.transcribe_provider
    if provider == "groq":
        words, language = _remote(path, settings, "groq")
    elif provider == "openai":
        words, language = _remote(path, settings, "openai")
    elif provider == "local":
        words, language = _local(path, settings)
    else:
        raise TranscribeError(f"TRANSCRIBE_PROVIDER desconhecido: {provider}")
    from app.pipeline.words import offset_words

    return offset_words(words, offset), language


def _remote(path: Path, settings: Settings, provider: str) -> tuple[list[Word], str]:
    if provider == "groq":
        if not settings.groq_api_key:
            raise TranscribeError("GROQ_API_KEY ausente")
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        token = settings.groq_api_key
        model = settings.groq_whisper_model
    else:
        if not settings.openai_api_key:
            raise TranscribeError("OPENAI_API_KEY ausente")
        url = "https://api.openai.com/v1/audio/transcriptions"
        token = settings.openai_api_key
        model = settings.openai_whisper_model
    data = [
        ("model", model),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
    ]
    if settings.transcribe_language:
        data.append(("language", settings.transcribe_language))
    with path.open("rb") as handle:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files={"file": (path.name, handle, "audio/flac")},
            timeout=600,
        )
    if response.status_code >= 400:
        raise TranscribeError(f"Transcrição {provider} falhou ({response.status_code}): {response.text[:500]}")
    return _words_from_verbose(response.json())


def _words_from_verbose(payload: object) -> tuple[list[Word], str]:
    if not isinstance(payload, dict):
        raise TranscribeError("Resposta de transcrição inesperada")
    raw_words = payload.get("words")
    words: list[Word] = []
    if isinstance(raw_words, list):
        for item in raw_words:
            if not isinstance(item, dict):
                continue
            text = item.get("word")
            start = item.get("start")
            end = item.get("end")
            if isinstance(text, str) and isinstance(start, (int, float)) and isinstance(end, (int, float)):
                words.append(Word(text.strip(), float(start), float(end)))
    language = payload.get("language")
    return words, language if isinstance(language, str) else ""


def _local(path: Path, settings: Settings) -> tuple[list[Word], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscribeError("faster-whisper não está instalado") from exc
    model = WhisperModel(settings.faster_whisper_model, device="cpu", compute_type="int8")
    language = settings.transcribe_language or None
    segments, info = model.transcribe(str(path), word_timestamps=True, language=language)
    words: list[Word] = []
    for segment in segments:
        segment_words = getattr(segment, "words", None) or []
        for token in segment_words:
            text = getattr(token, "word", "")
            start = getattr(token, "start", None)
            end = getattr(token, "end", None)
            if isinstance(text, str) and isinstance(start, (int, float)) and isinstance(end, (int, float)):
                words.append(Word(text.strip(), float(start), float(end)))
    detected = getattr(info, "language", "") or ""
    logger.info("local_transcribe words=%s", len(words))
    return words, detected


def words_to_json(words: list[Word]) -> str:
    return json.dumps([{"word": word.word, "start": word.start, "end": word.end} for word in words], ensure_ascii=False)


def words_from_json(raw: str) -> list[Word]:
    data = json.loads(raw)
    words: list[Word] = []
    if not isinstance(data, list):
        return words
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("word")
        start = item.get("start")
        end = item.get("end")
        if isinstance(text, str) and isinstance(start, (int, float)) and isinstance(end, (int, float)):
            words.append(Word(text, float(start), float(end)))
    return words
