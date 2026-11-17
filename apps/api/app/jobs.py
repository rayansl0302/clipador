import logging
import shutil
from pathlib import Path

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.postiz import PostizClient, PostizError
from app.models import Clip, Job, Project, Transcript, utcnow
from app.pipeline.framing import detect_subject_window
from app.pipeline.llm import suggest_clips
from app.pipeline.media import (
    MediaError,
    audio_energy,
    cleanup_temp,
    cut_audio,
    download_url,
    extract_audio,
    make_workdir,
    probe_duration,
    render_clip,
    require_limits,
)
from app.pipeline.transcribe import TranscribeError, transcribe_file, words_from_json, words_to_json
from app.pipeline.words import plan_chunks, text_of
from app.storage import get_storage

logger = logging.getLogger("clip.jobs")


def enqueue(session: Session, *, kind: str, project_id: str | None = None, clip_id: str | None = None) -> Job:
    job = Job(kind=kind, project_id=project_id, clip_id=clip_id, status="queued", progress=0, message="Na fila")
    session.add(job)
    session.commit()
    session.refresh(job)
    try:
        queue().enqueue(execute, job.id, job_timeout=60 * 60 * 6)
    except RedisError as exc:
        job.status = "failed"
        job.error_message = "Não foi possível falar com a fila"
        session.commit()
        raise RuntimeError("Fila indisponível") from exc
    return job


def queue() -> Queue:
    settings = get_settings()
    return Queue("default", connection=Redis.from_url(settings.redis_url))


def execute(job_id: str) -> None:
    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None:
            logger.error("job_missing id=%s", job_id)
            return
        job.status = "running"
        job.progress = 1
        job.message = "Em execução"
        job.updated_at = utcnow()
        session.commit()
        try:
            if job.kind == "ingest":
                _ingest(session, job)
            elif job.kind == "transcribe":
                _transcribe(session, job)
            elif job.kind == "suggest":
                _suggest(session, job)
            elif job.kind == "render":
                _render(session, job)
            elif job.kind == "frame":
                _frame(session, job)
            elif job.kind == "cleanup":
                removed = cleanup_temp(get_settings().cleanup_max_age_seconds)
                job.message = f"Removidos {removed} temporários"
            else:
                raise RuntimeError(f"Job desconhecido: {job.kind}")
        except (MediaError, TranscribeError, PostizError, OSError, RuntimeError, Exception) as exc:
            session.rollback()
            failed = session.get(Job, job_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:1000]
                failed.message = "Falhou"
                failed.updated_at = utcnow()
                _fail_owner(session, failed, str(exc)[:1000])
                session.commit()
            logger.info("job_failed id=%s error=%s", job_id, exc)
            return
        finished = session.get(Job, job_id)
        if finished is not None and finished.status == "running":
            finished.status = "done"
            finished.progress = 100
            finished.message = finished.message or "Concluído"
            finished.updated_at = utcnow()
            session.commit()
    finally:
        session.close()


def _touch(
    session: Session,
    job: Job,
    project: Project | None,
    progress: int,
    message: str,
    stage: str | None = None,
    update_project: bool = True,
) -> None:
    job.progress = progress
    job.message = message
    job.updated_at = utcnow()
    if project is not None and update_project:
        project.progress = progress
        project.status = "running"
        project.error_message = None
        project.updated_at = utcnow()
        if stage:
            project.stage = stage
    session.commit()


def _fail_owner(session: Session, job: Job, message: str) -> None:
    if job.project_id:
        project = session.get(Project, job.project_id)
        if project is not None:
            project.status = "failed"
            project.error_message = message
            project.updated_at = utcnow()
    if job.clip_id:
        clip = session.get(Clip, job.clip_id)
        if clip is not None:
            clip.status = "failed"
            clip.error_message = message
            clip.updated_at = utcnow()


def _ingest(session: Session, job: Job) -> None:
    project = _project(session, job)
    settings = get_settings()
    storage = get_storage()
    work = make_workdir()
    try:
        _touch(session, job, project, 5, "Baixando vídeo", "ingest")
        source = work / "source.mp4"
        if project.source_type == "url":
            if not project.source_url:
                raise MediaError("Projeto sem URL")
            download_url(project.source_url, source, settings.max_upload_bytes)
        else:
            if not project.video_key:
                raise MediaError("Upload sem arquivo")
            storage.download_file(project.video_key, str(source))
        duration = probe_duration(source)
        require_limits(source, duration, settings)
        project.duration_seconds = duration
        _touch(session, job, project, 40, "Enviando vídeo", "ingest")
        video_key = f"projects/{project.id}/source.mp4"
        storage.upload_file(str(source), video_key, "video/mp4")
        project.video_key = video_key
        _touch(session, job, project, 70, "Extraindo áudio", "ingest")
        audio = work / "audio.flac"
        extract_audio(source, audio)
        audio_key = f"projects/{project.id}/audio.flac"
        storage.upload_file(str(audio), audio_key, "audio/flac")
        project.audio_key = audio_key
        window = detect_subject_window(source)
        project.frame_x, project.frame_y, project.frame_w, project.frame_h = window
        session.commit()
        job.message = "Áudio extraído"
        enqueue(session, kind="transcribe", project_id=project.id)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _transcribe(session: Session, job: Job) -> None:
    project = _project(session, job)
    settings = get_settings()
    storage = get_storage()
    if not project.audio_key:
        raise MediaError("Áudio ainda não foi extraído")
    work = make_workdir()
    try:
        _touch(session, job, project, 35, "Baixando áudio", "transcribe")
        audio = work / "audio.flac"
        storage.download_file(project.audio_key, str(audio))
        duration = project.duration_seconds or probe_duration(audio)
        size = audio.stat().st_size
        if settings.transcribe_provider == "local":
            ranges = plan_chunks(duration, size, max(settings.transcribe_max_bytes, duration * 16000))
            if settings.local_chunk_seconds > 0 and duration > settings.local_chunk_seconds:
                ranges = plan_chunks(duration, int(duration * 1000), settings.local_chunk_seconds * 1000)
        else:
            ranges = plan_chunks(duration, size, settings.transcribe_max_bytes)
        words = []
        language = ""
        for index, (start, end) in enumerate(ranges, start=1):
            _touch(session, job, project, min(90, 35 + int(50 * index / max(len(ranges), 1))), f"Transcrevendo bloco {index}/{len(ranges)}", "transcribe")
            chunk_path = audio
            if len(ranges) > 1:
                chunk_path = work / f"chunk-{index}.flac"
                cut_audio(audio, chunk_path, start, end)
            chunk_words, detected = transcribe_file(chunk_path, settings, offset=start if len(ranges) > 1 else 0)
            if detected:
                language = detected
            words.extend(chunk_words)
        text = text_of(words)
        existing = session.scalar(select(Transcript).where(Transcript.project_id == project.id))
        if existing is None:
            existing = Transcript(project_id=project.id, provider=settings.transcribe_provider, language=language, text=text, words_json=words_to_json(words))
            session.add(existing)
        else:
            existing.provider = settings.transcribe_provider
            existing.language = language
            existing.text = text
            existing.words_json = words_to_json(words)
        session.commit()
        job.message = f"Transcrição com {len(words)} palavras"
        enqueue(session, kind="suggest", project_id=project.id)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _suggest(session: Session, job: Job) -> None:
    project = _project(session, job)
    settings = get_settings()
    transcript = session.scalar(select(Transcript).where(Transcript.project_id == project.id))
    if transcript is None:
        raise MediaError("Transcrição ausente")
    words = words_from_json(transcript.words_json)
    _touch(session, job, project, 80, "Sugerindo cortes", "suggest")
    energy: list[tuple[float, float]] = []
    if project.audio_key and (settings.llm_provider == "heuristic" or not settings.anthropic_api_key and settings.llm_provider == "anthropic"):
        work = make_workdir()
        try:
            audio = work / "audio.flac"
            get_storage().download_file(project.audio_key, str(audio))
            energy = audio_energy(audio)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    drafts, note = suggest_clips(words, settings, energy)
    suggested = session.scalars(select(Clip).where(Clip.project_id == project.id, Clip.status == "suggested")).all()
    for clip in suggested:
        session.delete(clip)
    for draft in drafts:
        session.add(
            Clip(
                project_id=project.id,
                start_seconds=draft.start,
                end_seconds=draft.end,
                score=draft.score,
                title=draft.title[:200],
                hook=draft.hook,
                reason=draft.reason,
                caption_text=draft.caption,
                status="suggested",
            )
        )
    project.status = "done"
    project.stage = "ready"
    project.progress = 100
    project.error_message = None
    project.updated_at = utcnow()
    job.message = f"{len(drafts)} cortes. {note}"
    session.commit()


def _render(session: Session, job: Job) -> None:
    if not job.clip_id:
        raise MediaError("Render sem clipe")
    clip = session.get(Clip, job.clip_id)
    project = _project(session, job)
    if clip is None:
        raise MediaError("Clipe não encontrado")
    if not project.video_key:
        raise MediaError("Vídeo de origem ausente")
    transcript = session.scalar(select(Transcript).where(Transcript.project_id == project.id))
    words = words_from_json(transcript.words_json) if transcript else []
    storage = get_storage()
    work = make_workdir()
    try:
        _touch(session, job, project, 20, f"Renderizando {clip.title or clip.id}", update_project=False)
        source = work / "source.mp4"
        output = work / "clip.mp4"
        storage.download_file(project.video_key, str(source))
        frame = None
        if None not in (project.frame_x, project.frame_y, project.frame_w, project.frame_h):
            frame = (project.frame_x, project.frame_y, project.frame_w, project.frame_h)
        render_clip(
            source,
            output,
            start=clip.start_seconds,
            end=clip.end_seconds,
            words=words,
            caption_text=clip.caption_text,
            font_name=clip.font_name,
            font_size=clip.font_size,
            primary_color=clip.primary_color,
            highlight_color=clip.highlight_color,
            position=clip.position,
            frame=frame,
            hook=clip.hook,
        )
        key = f"projects/{project.id}/clips/{clip.id}.mp4"
        storage.upload_file(str(output), key, "video/mp4")
        clip.rendered_key = key
        clip.status = "rendered"
        clip.error_message = None
        clip.updated_at = utcnow()
        job.message = "MP4 pronto"
        session.commit()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _frame(session: Session, job: Job) -> None:
    project = _project(session, job)
    if not project.video_key:
        raise MediaError("Vídeo de origem ausente")
    work = make_workdir()
    try:
        job.progress = 30
        job.message = "Procurando o rosto"
        job.updated_at = utcnow()
        session.commit()
        source = work / "source.mp4"
        get_storage().download_file(project.video_key, str(source))
        window = detect_subject_window(source)
        project.frame_x, project.frame_y, project.frame_w, project.frame_h = window
        project.updated_at = utcnow()
        job.message = "Rosto enquadrado"
        session.commit()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _project(session: Session, job: Job) -> Project:
    if not job.project_id:
        raise MediaError("Job sem projeto")
    project = session.get(Project, job.project_id)
    if project is None:
        raise MediaError("Projeto não encontrado")
    return project


def schedule_cleanup() -> None:
    session = SessionLocal()
    try:
        running = session.scalar(select(Job).where(Job.kind == "cleanup", Job.status.in_(["queued", "running"])))
        if running is not None:
            return
        enqueue(session, kind="cleanup")
    finally:
        session.close()
