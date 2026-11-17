"use client";

import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import type { Template } from "@/lib/types";

type Meta = {
  allow_signup: boolean;
  max_upload_bytes: number;
  max_video_duration_seconds: number;
  transcribe_provider: string;
  llm_provider: string;
  postiz_configured: boolean;
};

export default function SettingsPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [name, setName] = useState("Padrão");
  const [error, setError] = useState("");

  async function load() {
    try {
      setMeta(await api<Meta>("/meta"));
      setTemplates(await api<Template[]>("/caption-templates"));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao carregar");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createTemplate(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api("/caption-templates", {
        method: "POST",
        body: JSON.stringify({
          name,
          font_name: "DejaVu Sans",
          font_size: 72,
          primary_color: "#FFFFFF",
          highlight_color: "#E10600",
          position: "bottom",
        }),
      });
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao salvar");
    }
  }

  async function remove(id: string) {
    await api(`/caption-templates/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Ajustes</h1>
        <p className="mt-2 text-sm leading-6 text-mute">Limites deste estúdio e os templates de legenda da sua conta.</p>
      </div>
      {meta ? (
        <dl className="grid gap-4 rounded-2xl border border-line bg-sheet p-5 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-mute">Cadastro</dt>
            <dd className="mt-1 font-semibold">{meta.allow_signup ? "Aberto" : "Fechado"}</dd>
          </div>
          <div>
            <dt className="text-mute">Upload máximo</dt>
            <dd className="mt-1 font-semibold">{Math.round(meta.max_upload_bytes / (1024 * 1024))} MB</dd>
          </div>
          <div>
            <dt className="text-mute">Duração máxima</dt>
            <dd className="mt-1 font-semibold">{Math.round(meta.max_video_duration_seconds / 60)} min</dd>
          </div>
          <div>
            <dt className="text-mute">Transcrição</dt>
            <dd className="mt-1 font-semibold">{meta.transcribe_provider}</dd>
          </div>
          <div>
            <dt className="text-mute">Cortes</dt>
            <dd className="mt-1 font-semibold">{meta.llm_provider}</dd>
          </div>
          <div>
            <dt className="text-mute">Postiz</dt>
            <dd className="mt-1 font-semibold">{meta.postiz_configured ? "Configurado" : "Sem chave"}</dd>
          </div>
        </dl>
      ) : null}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Templates de legenda</h2>
        <form onSubmit={(event) => void createTemplate(event)} className="flex flex-col gap-3 sm:flex-row">
          <Input value={name} onChange={(event) => setName(event.target.value)} aria-label="Nome do template" />
          <Button className="shrink-0" type="submit">Salvar template</Button>
        </form>
        {error ? (
          <p className="text-sm text-signal" role="alert">
            {error}
          </p>
        ) : null}
        <ul className="flex flex-col gap-2">
          {templates.map((template) => (
            <li key={template.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-sheet px-3 py-2 text-sm">
              <span className="font-semibold">
                {template.name} · {template.position}
              </span>
              <Button size="sm" variant="ghost" onClick={() => void remove(template.id)}>
                Remover
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
