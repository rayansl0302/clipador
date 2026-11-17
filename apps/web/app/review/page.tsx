"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { clipStatusLabel } from "@/lib/labels";
import type { Clip } from "@/lib/types";

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

export default function ReviewPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api<Clip[]>("/review")
      .then((next) => {
        setClips(next);
        setLoaded(true);
      })
      .catch((caught: unknown) => setError(caught instanceof ApiError ? caught.message : "Falha ao carregar"));
  }, []);

  const groups = new Map<string, { title: string; clips: Clip[] }>();
  for (const clip of clips) {
    const current = groups.get(clip.project_id) ?? { title: clip.project_title || "Projeto", clips: [] };
    current.clips.push(clip);
    current.clips.sort((left, right) => left.start_seconds - right.start_seconds);
    groups.set(clip.project_id, current);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Revisão</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-mute">Cortes que ainda precisam de uma decisão, agrupados pelo vídeo de origem.</p>
      </div>
      {error ? (
        <p className="text-sm text-signal" role="alert">
          {error}
        </p>
      ) : null}
      {[...groups.entries()].map(([projectId, group]) => (
        <section key={projectId} className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">
            <Link href={`/projects/${projectId}`} className="text-ink">
              {group.title}
            </Link>
          </h2>
          <ul className="flex flex-col gap-2">
            {group.clips.map((clip) => (
              <li key={clip.id} className="rounded-2xl border border-line bg-sheet px-4 py-3">
                <p className="font-semibold text-ink">{clip.title || "Sem título"}</p>
                <p className="mt-1 text-sm text-mute">
                  {clipStatusLabel(clip.status)} · {clip.score}/100 · {formatClock(clip.start_seconds)}–{formatClock(clip.end_seconds)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {loaded && clips.length === 0 && !error ? <p className="text-sm text-mute">Nenhum corte esperando revisão.</p> : null}
    </div>
  );
}
