import Link from "next/link";

type ApiStatus = "ok" | "down";

function resolveServerApiUrl(raw: string | undefined): string | null {
  if (!raw) {
    return null;
  }
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw.replace(/\/$/, "");
  }
  return `http://${raw}`;
}

async function readApiStatus(): Promise<ApiStatus> {
  const apiUrl = resolveServerApiUrl(process.env.API_URL);
  if (!apiUrl) {
    return "down";
  }
  try {
    const response = await fetch(`${apiUrl}/health`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    if (!response.ok) {
      return "down";
    }
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "status" in body && body.status === "ok") {
      return "ok";
    }
    return "down";
  } catch {
    return "down";
  }
}

export default async function HomePage() {
  const status = await readApiStatus();
  return (
    <section className="flex max-w-2xl flex-col gap-8 py-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-4xl font-semibold tracking-tight text-ink">Do vídeo longo ao corte vertical.</h1>
        <p className="max-w-xl text-base leading-7 text-mute">
          Cole um link ou envie um arquivo. O estúdio transcreve, separa as partes e deixa a pessoa em cima, com a tela inteira embaixo.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/projects" className="inline-flex h-10 items-center rounded-lg bg-signal px-4 text-sm font-semibold text-white">
          Ir para projetos
        </Link>
        <Link href="/review" className="inline-flex h-10 items-center rounded-lg border border-line bg-sheet px-4 text-sm font-semibold text-ink">
          Revisar cortes
        </Link>
      </div>
      <p className="flex items-center gap-2 text-sm text-mute">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${status === "ok" ? "bg-ok" : "bg-signal"}`} aria-hidden="true" />
        {status === "ok" ? "O servidor está respondendo." : "O servidor não respondeu."}
      </p>
    </section>
  );
}
