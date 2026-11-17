function withScheme(value: string): string {
  if (value.startsWith("http://") || value.startsWith("https://")) {
    return value.replace(/\/$/, "");
  }
  return `http://${value}`;
}

export function GET(): Response {
  const raw = process.env.API_PUBLIC_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return Response.json({ apiUrl: withScheme(raw) });
}
