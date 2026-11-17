let cachedUrl: string | null = process.env.NEXT_PUBLIC_API_URL ?? null;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getApiUrl(): Promise<string> {
  if (cachedUrl) {
    return cachedUrl;
  }
  const response = await fetch("/api/runtime-config");
  const body: unknown = await response.json();
  if (typeof body === "object" && body !== null && "apiUrl" in body && typeof body.apiUrl === "string") {
    cachedUrl = body.apiUrl;
    return body.apiUrl;
  }
  throw new ApiError(500, "Configuração da API ausente");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${await getApiUrl()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let detail = "Não foi possível concluir a ação";
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(response.status, detail);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
