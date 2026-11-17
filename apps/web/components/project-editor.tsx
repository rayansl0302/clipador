"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input, TextArea } from "@/components/ui/input";
import { ApiError, api, getApiUrl } from "@/lib/api";
import { clipStatusLabel, jobKindLabel, projectStatusLabel, stageLabel } from "@/lib/labels";
import type { Channel, Clip, Job, Project, Template, Word } from "@/lib/types";

type EditorProps = { projectId: string };

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

function groupClips(clips: Clip[]): { name: string; clips: Clip[] }[] {
  const groups: { name: string; clips: Clip[] }[] = [];
  for (const clip of clips) {
    const match = /^Corte\s+\d+/.exec(clip.title);
    const name = match ? match[0] : "Outros cortes";
    const last = groups[groups.length - 1];
    if (last?.name === name) {
      last.clips.push(clip);
      continue;
    }
    groups.push({ name, clips: [clip] });
  }
  return groups;
}

function statusTone(status: string): string {
  if (status === "approved" || status === "rendered") {
    return "bg-ok-soft text-ok";
  }
  if (status === "rejected" || status === "failed") {
    return "bg-signal-soft text-signal";
  }
  return "bg-desk text-ink";
}

function spokenPhrase(words: Word[], start: number, end: number, time: number): { text: string; active: boolean }[] {
  const spoken = words.filter((word) => word.end > start && word.start < end);
  if (spoken.length === 0) {
    return [];
  }
  let index = spoken.findIndex((word) => time >= word.start && time < word.end);
  if (index < 0) {
    index = 0;
    for (let cursor = spoken.length - 1; cursor >= 0; cursor -= 1) {
      if (spoken[cursor].start <= time) {
        index = cursor;
        break;
      }
    }
  }
  const from = Math.max(0, index - 1);
  return spoken.slice(from, from + 3).map((word, offset) => ({
    text: word.word,
    active: from + offset === index && time >= word.start && time < word.end,
  }));
}

export function ProjectEditor({ projectId }: EditorProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const contentRef = useRef<HTMLVideoElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [clips, setClips] = useState<Clip[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [apiBase, setApiBase] = useState("");
  const [error, setError] = useState("");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [postContent, setPostContent] = useState("");
  const [when, setWhen] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [clipOffset, setClipOffset] = useState(0);
  const [playing, setPlaying] = useState(false);
  const orderedClips = [...clips].sort((left, right) => left.start_seconds - right.start_seconds);
  const clipGroups = groupClips(orderedClips);
  const selected = orderedClips.find((clip) => clip.id === selectedId) ?? null;
  const rangeRef = useRef<{ start: number; end: number } | null>(null);
  rangeRef.current = selected ? { start: selected.start_seconds, end: selected.end_seconds } : null;
  const clipLength = selected ? Math.max(0, selected.end_seconds - selected.start_seconds) : 0;
  const active =
    project?.status === "queued" ||
    project?.status === "running" ||
    (project?.jobs ?? []).some((job) => job.status === "queued" || job.status === "running");

  async function load() {
    try {
      const [nextProject, nextClips, transcript, nextTemplates] = await Promise.all([
        api<Project>(`/projects/${projectId}`),
        api<Clip[]>(`/projects/${projectId}/clips`),
        api<{ words: Word[] }>(`/projects/${projectId}/transcript`),
        api<Template[]>("/caption-templates"),
      ]);
      setProject(nextProject);
      setClips(nextClips);
      setWords(transcript.words);
      setTemplates(nextTemplates);
      const earliest = [...nextClips].sort((left, right) => left.start_seconds - right.start_seconds)[0];
      setSelectedId((current) => current ?? earliest?.id ?? null);
      setError("");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        window.location.href = "/login";
        return;
      }
      setError(caught instanceof ApiError ? caught.message : "Falha ao carregar");
    }
  }

  useEffect(() => {
    void getApiUrl().then(setApiBase);
    void load();
  }, [projectId]);

  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [active, projectId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.key === "j" || event.key === "k") {
        const ordered = [...clips].sort((left, right) => left.start_seconds - right.start_seconds);
        const index = ordered.findIndex((clip) => clip.id === selectedId);
        const next = event.key === "j" ? index + 1 : index - 1;
        const clip = ordered[next];
        if (clip) {
          setSelectedId(clip.id);
        }
      }
      if (event.key === "a" && selected) {
        void save({ status: "approved" });
      }
      if (event.key === "r" && selected) {
        void save({ status: "rejected" });
      }
      if (event.key === " ") {
        event.preventDefault();
        togglePlayback();
      }
      if ((event.key === "[" || event.key === "]") && selected) {
        const delta = event.key === "[" ? -0.2 : 0.2;
        void save({ start_seconds: Math.max(0, selected.start_seconds + delta) });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clips, selected, selectedId]);

  useEffect(() => {
    const video = videoRef.current;
    const range = rangeRef.current;
    if (!video || !range || video.readyState < 1) {
      return;
    }
    video.currentTime = range.start;
    if (contentRef.current) {
      contentRef.current.currentTime = range.start;
    }
    setClipOffset(0);
    void video.play();
    void contentRef.current?.play();
  }, [selectedId]);

  useEffect(() => {
    if (!project?.has_video || project.frame_w != null) {
      return;
    }
    let stopped = false;
    void api(`/projects/${projectId}/frame`, { method: "POST" }).catch(() => undefined);
    const timer = window.setInterval(() => {
      void api<Project>(`/projects/${projectId}`).then((next) => {
        if (stopped || next.frame_w == null) {
          return;
        }
        setProject(next);
        window.clearInterval(timer);
      });
    }, 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [project?.has_video, project?.frame_w, projectId]);

  useEffect(() => {
    const node = frameRef.current;
    if (!node || !project?.frame_w || !project.frame_h) {
      return;
    }
    const x = project.frame_x ?? 0;
    const y = project.frame_y ?? 0;
    node.style.setProperty("--frame-w", `${100 / project.frame_w}%`);
    node.style.setProperty("--frame-h", `${100 / project.frame_h}%`);
    node.style.setProperty("--frame-x", `${(-x / project.frame_w) * 100}%`);
    node.style.setProperty("--frame-y", `${(-y / project.frame_h) * 100}%`);
  }, [project?.frame_x, project?.frame_y, project?.frame_w, project?.frame_h]);

  function seek(seconds: number) {
    const video = videoRef.current;
    const range = rangeRef.current;
    if (!video) {
      return;
    }
    const target = range ? Math.min(Math.max(seconds, range.start), range.end) : seconds;
    video.currentTime = target;
    if (contentRef.current) {
      contentRef.current.currentTime = target;
    }
    setClipOffset(range ? target - range.start : 0);
    void video.play();
    void contentRef.current?.play();
  }

  function clampPlayback() {
    const video = videoRef.current;
    const range = rangeRef.current;
    if (!video || !range) {
      return;
    }
    if (video.currentTime < range.start) {
      video.currentTime = range.start;
    }
    if (video.currentTime >= range.end) {
      video.pause();
      if (video.currentTime > range.end) {
        video.currentTime = range.end;
      }
    }
    const content = contentRef.current;
    if (content && Math.abs(content.currentTime - video.currentTime) > 0.3) {
      content.currentTime = video.currentTime;
    }
    setClipOffset(Math.max(0, Math.min(video.currentTime, range.end) - range.start));
  }

  function onPlay() {
    const video = videoRef.current;
    const range = rangeRef.current;
    if (!video || !range) {
      return;
    }
    if (video.currentTime < range.start || video.currentTime >= range.end - 0.05) {
      video.currentTime = range.start;
    }
  }

  function togglePlayback() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (video.paused) {
      onPlay();
      void video.play();
      void contentRef.current?.play();
      return;
    }
    video.pause();
    contentRef.current?.pause();
  }

  async function save(patch: Partial<Clip>) {
    if (!selected) {
      return;
    }
    try {
      const updated = await api<Clip>(`/clips/${selected.id}`, { method: "PATCH", body: JSON.stringify(patch) });
      setClips((current) => current.map((clip) => (clip.id === updated.id ? updated : clip)));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao salvar");
    }
  }

  async function renderApproved() {
    await api(`/projects/${projectId}/render-approved`, { method: "POST" });
    await load();
  }

  async function renderOne() {
    if (!selected) {
      return;
    }
    await api(`/clips/${selected.id}/render`, { method: "POST" });
    await load();
  }

  async function retry() {
    try {
      await api(`/projects/${projectId}/retry`, { method: "POST" });
      await load();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        window.location.href = "/login";
        return;
      }
      setError(caught instanceof ApiError ? caught.message : "Falha ao reprocessar");
    }
  }

  async function loadChannels() {
    try {
      setChannels(await api<Channel[]>("/integrations/postiz/channels"));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Postiz indisponível");
    }
  }

  async function suggestCaption() {
    if (!selected) {
      return;
    }
    const result = await api<{ text: string }>(`/clips/${selected.id}/caption-suggestion`, { method: "POST" });
    setPostContent(result.text);
  }

  async function sendPostiz(event: FormEvent) {
    event.preventDefault();
    if (!selected) {
      return;
    }
    try {
      await api(`/clips/${selected.id}/postiz`, {
        method: "POST",
        body: JSON.stringify({
          integration_ids: chosen,
          content: postContent,
          scheduled_at: new Date(when).toISOString(),
          title: selected.title,
        }),
      });
      setError("");
      setPostContent("Enviado ao Postiz.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao enviar");
    }
  }

  const jobs = project?.jobs ?? [];

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="line-clamp-2 text-2xl font-semibold tracking-tight" title={project?.title ?? "Projeto"}>{project?.title ?? "Projeto"}</h1>
          <p className="mt-1 text-sm text-mute">
            {[
              project?.channel,
              project?.status === "done"
                ? stageLabel(project.stage)
                : `${stageLabel(project?.stage ?? "")} · ${projectStatusLabel(project?.status ?? "")}${project ? ` · ${project.progress}%` : ""}`,
            ].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => void retry()}>
            Reprocessar
          </Button>
          <a className={buttonVariants({ variant: "secondary" })} href={apiBase ? `${apiBase}/projects/${projectId}/export.zip` : undefined}>
            Exportar zip
          </a>
          <Button onClick={() => void renderApproved()}>Renderizar aprovados</Button>
        </div>
      </div>
      {project?.error_message ? <p className="text-sm text-signal" role="alert">{project.error_message}</p> : null}
      {error ? <p className="text-sm text-signal" role="alert">{error}</p> : null}
      <div className="grid items-start gap-8 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="mx-auto flex w-full max-w-[340px] flex-col gap-4 lg:sticky lg:top-6 lg:mx-0">
          <h2 className="text-sm font-semibold">Prévia do corte</h2>
          {project?.has_video ? (
            <div className="preview-stage aspect-[9/16] overflow-hidden rounded-lg bg-black">
              <div ref={frameRef} className={`preview-face ${project?.frame_w ? "is-framed" : ""}`}>
                <video
                  ref={videoRef}
                  playsInline
                  crossOrigin="use-credentials"
                  src={apiBase ? `${apiBase}/projects/${projectId}/media` : undefined}
                  onLoadedMetadata={clampPlayback}
                  onTimeUpdate={clampPlayback}
                  onPlay={() => {
                    onPlay();
                    const content = contentRef.current;
                    const video = videoRef.current;
                    if (content && video) {
                      content.currentTime = video.currentTime;
                      void content.play();
                    }
                    setPlaying(true);
                  }}
                  onPause={() => {
                    contentRef.current?.pause();
                    setPlaying(false);
                  }}
                  onSeeked={clampPlayback}
                />
              </div>
              <div className="preview-content">
                <video
                  ref={contentRef}
                  muted
                  playsInline
                  crossOrigin="use-credentials"
                  src={apiBase ? `${apiBase}/projects/${projectId}/media` : undefined}
                />
              </div>
              {selected ? (
                <div className="preview-captions">
                  {selected.hook ? <p className="caption-hook">{selected.hook}</p> : null}
                  <p className="caption-line">
                    {spokenPhrase(words, selected.start_seconds, selected.end_seconds, selected.start_seconds + clipOffset).map((item, index) => (
                      <span key={`${item.text}-${index}`} className={item.active ? "caption-word caption-word-active" : "caption-word"}>
                        {item.text}{" "}
                      </span>
                    ))}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-mute">O vídeo aparece quando a ingestão termina.</p>
          )}
          {selected ? (
            <>
              <div className="flex items-center justify-between gap-3 text-sm">
                <Button size="sm" onClick={togglePlayback}>{playing ? "Pausar" : "Tocar trecho"}</Button>
                <span className="text-mute">
                  {formatClock(clipOffset)} / {formatClock(clipLength)}
                </span>
              </div>
              <input
                className="h-2 w-full accent-signal"
                type="range"
                min={0}
                max={clipLength}
                step={0.1}
                value={Math.min(clipOffset, clipLength)}
                aria-label="Posição no corte"
                onChange={(event) => seek(selected.start_seconds + Number(event.target.value))}
              />
              <p className="text-xs leading-5 text-mute">
                Só este trecho toca, de {formatClock(selected.start_seconds)} a {formatClock(selected.end_seconds)}. Em cima a pessoa, embaixo a tela inteira.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => void save({ status: "approved" })}>Aprovar</Button>
                <Button size="sm" variant="danger" onClick={() => void save({ status: "rejected" })}>Rejeitar</Button>
                <Button size="sm" variant="secondary" onClick={() => void renderOne()}>Renderizar MP4</Button>
                {selected.has_file ? (
                  <a className={buttonVariants({ variant: "secondary", size: "sm" })} href={apiBase ? `${apiBase}/clips/${selected.id}/media` : undefined}>
                    Abrir MP4
                  </a>
                ) : null}
              </div>
              <p className="text-xs leading-5 text-mute">J e K trocam o corte. A aprova, R rejeita, colchetes ajustam o início, espaço toca.</p>
            </>
          ) : (
            <p className="text-sm text-mute">Escolha um corte na lista.</p>
          )}
        </div>
        <div className="flex max-h-[75vh] flex-col gap-5 overflow-auto pr-1">
          {orderedClips.length === 0 ? <p className="text-sm text-mute">Nenhum corte neste projeto.</p> : null}
          {clipGroups.map((group) => (
            <section key={group.name} className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-mute">{group.name}</h2>
              <ul className="flex flex-col gap-2">
                {group.clips.map((clip) => (
                  <li key={clip.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(clip.id)}
                      className={`w-full rounded-2xl border p-3 text-left ${clip.id === selectedId ? "border-signal bg-sheet" : "border-line bg-sheet hover:border-ink"}`}
                    >
                      <span className="block text-sm font-semibold">{clip.title || "Sem título"}</span>
                      <span className="mt-2 flex flex-wrap items-center gap-2 text-xs text-mute">
                        <span className={`rounded-full px-2 py-0.5 font-semibold ${statusTone(clip.status)}`}>{clipStatusLabel(clip.status)}</span>
                        <span>{clip.score}/100</span>
                        <span>{formatClock(clip.start_seconds)}–{formatClock(clip.end_seconds)}</span>
                        <span>{formatClock(clip.end_seconds - clip.start_seconds)}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
      <section className="rounded-2xl border border-line bg-sheet p-4">
        <h2 className="text-sm font-semibold">Transcrição</h2>
        <div className="mt-3 max-h-48 overflow-auto text-sm leading-7">
          {words.length === 0 ? <p className="text-mute">A transcrição aparece quando o áudio tiver fala.</p> : null}
          {words.map((word, index) => (
            <button key={`${word.start}-${index}`} className="mr-1 rounded text-ink hover:text-signal" onClick={() => seek(word.start)} type="button">
              {word.word}
            </button>
          ))}
        </div>
      </section>
      {selected ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="grid gap-4 rounded-2xl border border-line bg-sheet p-5">
            <h2 className="text-lg font-semibold">Ajustar este corte</h2>
            <label className="flex flex-col gap-1.5 text-sm font-semibold">
              Início
              <Input type="number" step="0.1" value={selected.start_seconds} onChange={(event) => void save({ start_seconds: Number(event.target.value) })} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-semibold">
              Fim
              <Input type="number" step="0.1" value={selected.end_seconds} onChange={(event) => void save({ end_seconds: Number(event.target.value) })} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-semibold">
              Título
              <Input value={selected.title} onChange={(event) => void save({ title: event.target.value })} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-semibold">
              Legenda
              <TextArea value={selected.caption_text} onChange={(event) => void save({ caption_text: event.target.value })} />
            </label>
            <p className="text-sm text-mute">Gancho: {selected.hook || "nenhum"}</p>
            <div className="flex flex-wrap gap-2">
              {templates.map((template) => (
                <Button key={template.id} size="sm" variant="ghost" onClick={() => void api(`/clips/${selected.id}/apply-template/${template.id}`, { method: "POST" }).then(load)}>
                  {template.name}
                </Button>
              ))}
            </div>
          </section>
          <form onSubmit={(event) => void sendPostiz(event)} className="flex flex-col gap-3 rounded-2xl border border-line bg-sheet p-5">
            <h2 className="text-lg font-semibold">Publicar</h2>
            <p className="text-sm text-mute">O envio só libera depois que o MP4 deste corte existir.</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => void loadChannels()}>Carregar canais</Button>
              <Button variant="ghost" onClick={() => void suggestCaption()}>Sugerir texto</Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {channels.map((channel) => (
                <label key={channel.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={chosen.includes(channel.id)}
                    onChange={(event) =>
                      setChosen((current) => (event.target.checked ? [...current, channel.id] : current.filter((id) => id !== channel.id)))
                    }
                  />
                  {channel.name} ({channel.identifier})
                </label>
              ))}
            </div>
            <TextArea value={postContent} onChange={(event) => setPostContent(event.target.value)} placeholder="Texto e hashtags" aria-label="Texto da publicação" />
            <Input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} required aria-label="Data da publicação" />
            <Button type="submit" disabled={!selected.has_file}>Enviar ao Postiz</Button>
          </form>
        </div>
      ) : null}
      {jobs.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs text-mute">
          {jobs.map((job: Job) => (
            <li key={job.id}>
              {jobKindLabel(job.kind)} · {projectStatusLabel(job.status)} · {job.progress}% · {job.message || job.error_message || ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
