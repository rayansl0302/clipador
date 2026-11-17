"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { projectStatusLabel, stageLabel } from "@/lib/labels";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState<Project | null>(null);
  const [phrase, setPhrase] = useState("");
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState("");
  const busy = projects.some((project) => project.status === "queued" || project.status === "running");

  async function load() {
    try {
      setProjects(await api<Project[]>("/projects"));
      setError("");
      setLoaded(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao listar");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!pending) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !removing) {
        setPending(null);
        setPhrase("");
        setRemoveError("");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, removing]);

  useEffect(() => {
    if (!busy) {
      return;
    }
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function createUrl(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api("/projects/url", { method: "POST", body: JSON.stringify({ url }) });
      setUrl("");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao criar");
    }
  }

  function askRemoval(project: Project) {
    setPending(project);
    setPhrase("");
    setRemoveError("");
  }

  async function removeProject(event: FormEvent) {
    event.preventDefault();
    if (!pending || phrase.trim() !== "eu aceito") {
      return;
    }
    setRemoving(true);
    setRemoveError("");
    try {
      await api(`/projects/${pending.id}`, { method: "DELETE", body: JSON.stringify({ confirm: phrase.trim() }) });
      setPending(null);
      setPhrase("");
      await load();
    } catch (caught) {
      setRemoveError(caught instanceof ApiError ? caught.message : "Falha ao remover");
    } finally {
      setRemoving(false);
    }
  }

  async function upload(file: File) {
    setError("");
    const body = new FormData();
    body.set("file", file);
    body.set("title", file.name);
    try {
      await api("/projects/upload", { method: "POST", body });
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha no upload");
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Projetos</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-mute">Comece por um link ou por um arquivo. A lista atualiza enquanto o vídeo é preparado.</p>
      </div>
      <form onSubmit={(event) => void createUrl(event)} className="flex flex-col gap-4 rounded-2xl border border-line bg-sheet p-5">
        <label className="flex flex-col gap-2 text-sm font-semibold" htmlFor="video-url">
          Link do vídeo
          <Input id="video-url" placeholder="https://www.youtube.com/watch?v=" value={url} onChange={(event) => setUrl(event.target.value)} required />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit">Começar pelo link</Button>
          <label className="inline-flex h-10 cursor-pointer items-center rounded-lg border border-line bg-white px-4 text-sm font-semibold text-ink focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-signal">
            Enviar arquivo
            <input
              className="sr-only"
              type="file"
              accept="video/*"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  void upload(file);
                }
              }}
            />
          </label>
        </div>
      </form>
      {error ? (
        <p className="text-sm text-signal" role="alert">
          {error}
        </p>
      ) : null}
      {loaded && projects.length === 0 ? <p className="text-sm text-mute">Nenhum vídeo ainda. O primeiro corte começa no campo acima.</p> : null}
      <ul className="flex flex-col gap-3">
        {projects.map((project) => {
          const unnamed = project.title.startsWith("http");
          const status = project.status === "done" ? stageLabel(project.stage) : `${stageLabel(project.stage)} · ${projectStatusLabel(project.status)}`;
          return (
            <li key={project.id} className="flex items-center gap-3 rounded-2xl border border-line bg-sheet p-4 hover:border-ink">
              <Link href={`/projects/${project.id}`} className="flex min-w-0 flex-1 items-center justify-between gap-4 rounded-xl">
                {project.thumbnail_url?.startsWith("https://") ? (
                  <img src={project.thumbnail_url} alt="" className="h-16 w-28 shrink-0 rounded-lg object-cover" />
                ) : null}
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-ink">{unnamed ? "Vídeo por link" : project.title}</span>
                  {project.channel ? <span className="mt-1 block truncate text-sm text-mute">{project.channel}</span> : null}
                  {unnamed ? <span className="mt-1 block truncate text-sm text-mute">{project.title}</span> : null}
                  <span className="mt-2 block text-sm text-mute">{status}</span>
                  {project.progress < 100 ? <progress className="meter mt-3" value={project.progress} max={100} aria-label={`Progresso de ${project.title}`} /> : null}
                  {project.error_message ? <span className="mt-2 block text-sm text-signal">{project.error_message}</span> : null}
                </span>
                <span className="shrink-0 rounded-lg bg-signal px-3 py-2 text-sm font-semibold text-white">Abrir</span>
              </Link>
              <Button type="button" variant="danger" size="sm" onClick={() => askRemoval(project)}>
                Remover
              </Button>
            </li>
          );
        })}
      </ul>
      {pending ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
          onClick={() => {
            if (!removing) {
              setPending(null);
              setPhrase("");
              setRemoveError("");
            }
          }}
        >
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-project-title"
            className="w-full max-w-md rounded-2xl border border-line bg-sheet p-5"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void removeProject(event)}
          >
            <h2 id="remove-project-title" className="text-xl font-semibold">
              Remover projeto
            </h2>
            <p className="mt-2 text-sm leading-6 text-mute">
              {pending.title} sai da lista junto com os cortes e os arquivos. Para confirmar, digite <strong className="text-ink">eu aceito</strong>.
            </p>
            <label className="mt-4 flex flex-col gap-2 text-sm font-semibold" htmlFor="remove-confirm">
              Confirmação
              <Input id="remove-confirm" value={phrase} onChange={(event) => setPhrase(event.target.value)} autoFocus autoComplete="off" />
            </label>
            {removeError ? (
              <p className="mt-3 text-sm text-signal" role="alert">
                {removeError}
              </p>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-3">
              <Button
                type="button"
                variant="secondary"
                disabled={removing}
                onClick={() => {
                  setPending(null);
                  setPhrase("");
                  setRemoveError("");
                }}
              >
                Cancelar
              </Button>
              <Button type="submit" variant="danger" disabled={removing || phrase.trim() !== "eu aceito"}>
                {removing ? "Removendo" : "Remover"}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
