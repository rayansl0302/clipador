"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";

const links = [
  { href: "/", label: "Início" },
  { href: "/projects", label: "Projetos" },
  { href: "/review", label: "Revisão" },
  { href: "/settings", label: "Ajustes" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api<{ email: string }>("/auth/me")
      .then((user) => setEmail(user.email))
      .catch(() => setEmail(null));
  }, [pathname]);

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setEmail(null);
      setNotice("");
      router.push("/login");
    } catch (caught) {
      setNotice(caught instanceof ApiError ? caught.message : "Não foi possível sair");
    }
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="border-b border-line bg-sheet md:min-h-screen md:border-r md:border-b-0">
        <div className="flex flex-col gap-6 px-4 py-4 md:sticky md:top-0 md:h-screen md:py-6">
          <Link href="/" className="text-lg font-semibold tracking-tight text-ink">
            Clip Studio
          </Link>
          <nav className="flex flex-wrap gap-1 md:flex-col" aria-label="Principal">
            {links.map((link) => {
              const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-3 py-2 text-sm font-semibold ${active ? "bg-desk text-ink" : "text-mute hover:bg-desk hover:text-ink"}`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto flex flex-col gap-2 text-sm">
            {email ? (
              <>
                <p className="truncate text-mute" title={email}>
                  {email}
                </p>
                <Button size="sm" variant="secondary" onClick={() => void logout()}>
                  Sair
                </Button>
              </>
            ) : (
              <Link href="/login" className="font-semibold text-signal">
                Entrar
              </Link>
            )}
            {notice ? (
              <p className="text-signal" role="alert">
                {notice}
              </p>
            ) : null}
          </div>
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
