import io
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete as sql_delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.integrations.postiz import PostizClient, PostizError, platform_settings
from app.jobs import enqueue
from app.models import CaptionTemplate, Clip, Job, Project, Transcript, User, utcnow
from app.pipeline.llm import suggest_publish_text
from app.pipeline.source_ref import youtube_reference
from app.pipeline.media import make_workdir
from app.pipeline.transcribe import words_from_json
from app.security import clear_session_cookie, hash_password, read_token, set_session_cookie, verify_password
from app.storage import Storage, get_storage

router = APIRouter()


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class UrlProjectBody(BaseModel):
    url: str
    title: str = ""


class ClipPatch(BaseModel):
    start_seconds: float | None = None
    end_seconds: float | None = None
    title: str | None = None
    hook: str | None = None
    caption_text: str | None = None
    status: str | None = None
    font_name: str | None = None
    font_size: int | None = None
    primary_color: str | None = None
    highlight_color: str | None = None
    position: str | None = None


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    font_name: str = "DejaVu Sans"
    font_size: int = 72
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFE14A"
    position: str = "bottom"


class DeleteProjectBody(BaseModel):
    confirm: str = ""


REMOVAL_PHRASE = "eu aceito"


def removal_accepted(confirm: str) -> bool:
    return confirm.strip() == REMOVAL_PHRASE


class PostizBody(BaseModel):
    integration_ids: list[str] = Field(min_length=1)
    content: str = Field(min_length=1)
    scheduled_at: datetime
    title: str = ""


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Faça login")
    user_id = read_token(token, settings)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return user


def _project_or_404(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return project


def _clip_or_404(db: Session, user: User, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    project = db.get(Project, clip.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    return clip


def _dump_project(project: Project) -> dict[str, object]:
    return {
        "id": project.id,
        "title": project.title,
        "channel": project.channel,
        "thumbnail_url": project.thumbnail_url,
        "source_type": project.source_type,
        "source_url": project.source_url,
        "status": project.status,
        "stage": project.stage,
        "progress": project.progress,
        "error_message": project.error_message,
        "duration_seconds": project.duration_seconds,
        "has_video": bool(project.video_key),
        "has_audio": bool(project.audio_key),
        "frame_x": project.frame_x,
        "frame_y": project.frame_y,
        "frame_w": project.frame_w,
        "frame_h": project.frame_h,
        "created_at": project.created_at.isoformat(),
    }


def _dump_job(job: Job) -> dict[str, object]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error_message": job.error_message,
        "clip_id": job.clip_id,
        "created_at": job.created_at.isoformat(),
    }


def _dump_clip(clip: Clip) -> dict[str, object]:
    return {
        "id": clip.id,
        "project_id": clip.project_id,
        "start_seconds": clip.start_seconds,
        "end_seconds": clip.end_seconds,
        "score": clip.score,
        "title": clip.title,
        "hook": clip.hook,
        "reason": clip.reason,
        "status": clip.status,
        "caption_text": clip.caption_text,
        "font_name": clip.font_name,
        "font_size": clip.font_size,
        "primary_color": clip.primary_color,
        "highlight_color": clip.highlight_color,
        "position": clip.position,
        "has_file": bool(clip.rendered_key),
        "error_message": clip.error_message,
    }


@router.post("/auth/signup")
def signup(body: SignupBody, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    settings = get_settings()
    if not settings.allow_signup:
        raise HTTPException(status_code=403, detail="Cadastro desativado")
    email = body.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    set_session_cookie(response, user.id, settings)
    return {"id": user.id, "email": user.email}


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    set_session_cookie(response, user.id)
    return {"id": user.id, "email": user.email}


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, str]:
    return {"id": user.id, "email": user.email}


@router.get("/meta")
def meta() -> dict[str, object]:
    settings = get_settings()
    return {
        "allow_signup": settings.allow_signup,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_video_duration_seconds": settings.max_video_duration_seconds,
        "transcribe_provider": settings.transcribe_provider,
        "llm_provider": settings.llm_provider,
        "postiz_configured": bool(settings.postiz_url and settings.postiz_api_key),
    }


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())).all()
    return [_dump_project(row) for row in rows]


@router.post("/projects/url")
def create_from_url(body: UrlProjectBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Informe um link http(s)")
    supplied = body.title.strip()
    reference = youtube_reference(url)
    channel = reference[1] if reference else None
    thumbnail = reference[2] if reference else None
    title = supplied or (reference[0] if reference else url[:80])
    project = Project(
        user_id=user.id,
        title=title[:200],
        channel=channel,
        thumbnail_url=thumbnail,
        source_type="url",
        source_url=url,
        status="queued",
        stage="ingest",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    try:
        enqueue(db, kind="ingest", project_id=project.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _dump_project(project)


@router.post("/projects/upload")
async def create_from_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    name = file.filename or "video.mp4"
    project = Project(user_id=user.id, title=(title.strip() or name)[:200], source_type="upload", status="queued", stage="ingest")
    db.add(project)
    db.commit()
    db.refresh(project)
    work = make_workdir()
    destination = work / "upload.mp4"
    try:
        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    db.delete(project)
                    db.commit()
                    raise HTTPException(status_code=413, detail="Arquivo maior que o limite")
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio")
        key = f"projects/{project.id}/source.mp4"
        get_storage().upload_file(str(destination), key, file.content_type or "video/mp4")
        project.video_key = key
        db.commit()
        enqueue(db, kind="ingest", project_id=project.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    db.refresh(project)
    return _dump_project(project)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    body: DeleteProjectBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not removal_accepted(body.confirm):
        raise HTTPException(status_code=400, detail="Digite eu aceito para remover")
    project = _project_or_404(db, user, project_id)
    try:
        get_storage().delete_prefix(f"projects/{project.id}/")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível apagar os arquivos") from exc
    clip_ids = list(db.scalars(select(Clip.id).where(Clip.project_id == project.id)).all())
    if clip_ids:
        db.execute(update(Job).where(Job.clip_id.in_(clip_ids)).values(clip_id=None))
    db.execute(sql_delete(Job).where(Job.project_id == project.id))
    db.execute(sql_delete(Clip).where(Clip.project_id == project.id))
    db.execute(sql_delete(Transcript).where(Transcript.project_id == project.id))
    db.delete(project)
    db.commit()
    return {"status": "ok"}


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    project = _project_or_404(db, user, project_id)
    jobs = db.scalars(select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc())).all()
    payload = _dump_project(project)
    payload["jobs"] = [_dump_job(job) for job in jobs]
    return payload


@router.get("/projects/{project_id}/transcript")
def get_transcript(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    project = _project_or_404(db, user, project_id)
    transcript = db.scalar(select(Transcript).where(Transcript.project_id == project.id))
    if transcript is None:
        return {"words": [], "text": "", "provider": None}
    return {
        "provider": transcript.provider,
        "language": transcript.language,
        "text": transcript.text,
        "words": [{"word": word.word, "start": word.start, "end": word.end} for word in words_from_json(transcript.words_json)],
    }


@router.post("/projects/{project_id}/retry")
def retry_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    project = _project_or_404(db, user, project_id)
    transcript = db.scalar(select(Transcript).where(Transcript.project_id == project.id))
    if not project.audio_key:
        kind = "ingest"
    elif transcript is None:
        kind = "transcribe"
    else:
        kind = "suggest"
    project.status = "queued"
    project.error_message = None
    db.commit()
    try:
        job = enqueue(db, kind=kind, project_id=project.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"job_id": job.id, "kind": kind}


@router.post("/projects/{project_id}/frame")
def frame_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    project = _project_or_404(db, user, project_id)
    if project.frame_w is not None:
        return _dump_project(project)
    active = db.scalar(
        select(Job).where(
            Job.project_id == project.id,
            Job.kind == "frame",
            Job.status.in_(("queued", "running")),
        )
    )
    if active is None:
        try:
            enqueue(db, kind="frame", project_id=project.id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _dump_project(project)


@router.get("/projects/{project_id}/clips")
def list_clips(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    project = _project_or_404(db, user, project_id)
    clips = db.scalars(select(Clip).where(Clip.project_id == project.id).order_by(Clip.score.desc(), Clip.start_seconds)).all()
    return [_dump_clip(clip) for clip in clips]


@router.get("/review")
def review_queue(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.execute(
        select(Clip, Project)
        .join(Project, Project.id == Clip.project_id)
        .where(Project.user_id == user.id, Clip.status == "suggested")
        .order_by(Project.created_at.desc(), Clip.score.desc())
    ).all()
    return [{**_dump_clip(clip), "project_title": project.title} for clip, project in rows]


@router.patch("/clips/{clip_id}")
def update_clip(clip_id: str, body: ClipPatch, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    clip = _clip_or_404(db, user, clip_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in {"suggested", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Status inválido")
    if "position" in data and data["position"] not in {"bottom", "middle", "top"}:
        raise HTTPException(status_code=400, detail="Posição inválida")
    for key, value in data.items():
        setattr(clip, key, value)
    if clip.end_seconds <= clip.start_seconds:
        raise HTTPException(status_code=400, detail="O fim precisa ser depois do início")
    clip.updated_at = utcnow()
    db.commit()
    db.refresh(clip)
    return _dump_clip(clip)


@router.post("/clips/{clip_id}/render")
def render_one(clip_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    clip = _clip_or_404(db, user, clip_id)
    clip.status = "approved"
    db.commit()
    try:
        job = enqueue(db, kind="render", project_id=clip.project_id, clip_id=clip.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"job_id": job.id}


@router.post("/projects/{project_id}/render-approved")
def render_approved(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    project = _project_or_404(db, user, project_id)
    clips = db.scalars(select(Clip).where(Clip.project_id == project.id, Clip.status == "approved")).all()
    count = 0
    for clip in clips:
        try:
            enqueue(db, kind="render", project_id=project.id, clip_id=clip.id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        count += 1
    return {"queued": count}


@router.get("/projects/{project_id}/media")
def stream_source(project_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    project = _project_or_404(db, user, project_id)
    if not project.video_key:
        raise HTTPException(status_code=404, detail="Vídeo ainda não está pronto")
    return _stream(get_storage(), project.video_key, request, "video/mp4")


@router.get("/clips/{clip_id}/media")
def stream_clip(clip_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    clip = _clip_or_404(db, user, clip_id)
    if not clip.rendered_key:
        raise HTTPException(status_code=404, detail="Clipe ainda não foi renderizado")
    return _stream(get_storage(), clip.rendered_key, request, "video/mp4")


@router.get("/clips/{clip_id}/download")
def download_clip(clip_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    clip = _clip_or_404(db, user, clip_id)
    if not clip.rendered_key:
        raise HTTPException(status_code=404, detail="Clipe ainda não foi renderizado")
    return {"url": get_storage().signed_url(clip.rendered_key)}


@router.get("/projects/{project_id}/export.zip")
def export_zip(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    project = _project_or_404(db, user, project_id)
    clips = db.scalars(select(Clip).where(Clip.project_id == project.id, Clip.rendered_key.is_not(None))).all()
    if not clips:
        raise HTTPException(status_code=404, detail="Nenhum clipe renderizado")
    storage = get_storage()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for index, clip in enumerate(clips, start=1):
            if not clip.rendered_key:
                continue
            work = make_workdir()
            path = work / "clip.mp4"
            try:
                storage.download_file(clip.rendered_key, str(path))
                archive.write(path, arcname=f"{index:02d}-{_safe_name(clip.title)}.mp4")
            finally:
                shutil.rmtree(work, ignore_errors=True)
    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{project.id}.zip"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@router.get("/caption-templates")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(CaptionTemplate).where(CaptionTemplate.user_id == user.id).order_by(CaptionTemplate.name)).all()
    return [_dump_template(row) for row in rows]


@router.post("/caption-templates")
def create_template(body: TemplateBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    if body.position not in {"bottom", "middle", "top"}:
        raise HTTPException(status_code=400, detail="Posição inválida")
    row = CaptionTemplate(user_id=user.id, **body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um template com esse nome") from exc
    db.refresh(row)
    return _dump_template(row)


@router.delete("/caption-templates/{template_id}")
def delete_template(template_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.get(CaptionTemplate, template_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@router.post("/clips/{clip_id}/apply-template/{template_id}")
def apply_template(clip_id: str, template_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    clip = _clip_or_404(db, user, clip_id)
    template = db.get(CaptionTemplate, template_id)
    if template is None or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    clip.font_name = template.font_name
    clip.font_size = template.font_size
    clip.primary_color = template.primary_color
    clip.highlight_color = template.highlight_color
    clip.position = template.position
    clip.updated_at = utcnow()
    db.commit()
    return _dump_clip(clip)


@router.post("/clips/{clip_id}/caption-suggestion")
def caption_suggestion(clip_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    clip = _clip_or_404(db, user, clip_id)
    text = suggest_publish_text(clip.title, clip.hook, clip.caption_text, get_settings())
    return {"text": text}


@router.get("/integrations/postiz/channels")
def postiz_channels(user: User = Depends(current_user)) -> list[dict[str, object]]:
    del user
    client = _postiz()
    try:
        rows = client.list_integrations()
    except PostizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "identifier": row.get("identifier"),
            "disabled": row.get("disabled", False),
            "profile": row.get("profile"),
        }
        for row in rows
    ]


@router.post("/clips/{clip_id}/postiz")
def send_postiz(clip_id: str, body: PostizBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    clip = _clip_or_404(db, user, clip_id)
    if not clip.rendered_key:
        raise HTTPException(status_code=400, detail="Renderize o clipe antes de enviar")
    client = _postiz()
    work = make_workdir()
    path = work / "clip.mp4"
    try:
        get_storage().download_file(clip.rendered_key, str(path))
        uploaded = client.upload_file(path)
        channels = {str(item.get("id")): str(item.get("identifier") or "") for item in client.list_integrations()}
        selected: list[tuple[str, str]] = []
        for integration_id in body.integration_ids:
            if integration_id not in channels:
                raise HTTPException(status_code=400, detail=f"Canal não encontrado: {integration_id}")
            selected.append((integration_id, channels[integration_id]))
        when = body.scheduled_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        created = client.create_scheduled_post(
            integration_ids=selected,
            content=body.content,
            when_iso=when,
            media_id=str(uploaded["id"]),
            media_path=str(uploaded["path"]),
            title=body.title or clip.title,
        )
    except PostizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"postiz": created, "settings_preview": [platform_settings(identifier, body.title or clip.title) for _, identifier in selected]}


def _postiz() -> PostizClient:
    settings = get_settings()
    if not settings.postiz_url or not settings.postiz_api_key:
        raise HTTPException(status_code=503, detail="Defina POSTIZ_URL e POSTIZ_API_KEY")
    return PostizClient(settings.postiz_url, settings.postiz_api_key)


def _dump_template(row: CaptionTemplate) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "font_name": row.font_name,
        "font_size": row.font_size,
        "primary_color": row.primary_color,
        "highlight_color": row.highlight_color,
        "position": row.position,
    }


def _stream(storage: Storage, key: str, request: Request, media_type: str) -> StreamingResponse:
    size = storage.size(key)
    range_header = request.headers.get("range")
    start, end = _range(range_header, size)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    status = 206 if range_header else 200
    return StreamingResponse(storage.iter_bytes(key, start, end), status_code=status, media_type=media_type, headers=headers)


def _range(header: str | None, size: int) -> tuple[int, int]:
    if not header or not header.startswith("bytes="):
        return 0, size - 1
    raw = header.removeprefix("bytes=").split("-", 1)
    start_text, end_text = raw[0], raw[1] if len(raw) > 1 else ""
    start = int(start_text) if start_text else 0
    end = int(end_text) if end_text else size - 1
    end = min(end, size - 1)
    if start > end or start < 0:
        raise HTTPException(status_code=416, detail="Intervalo inválido")
    return start, end


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned[:40] or "clipe"
