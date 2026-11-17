"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

type AuthFormProps = {
  mode: "login" | "signup";
};

export function AuthForm({ mode }: AuthFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api(mode === "login" ? "/auth/login" : "/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      window.location.href = "/projects";
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Falha ao entrar");
    }
  }

  const title = mode === "login" ? "Entrar" : "Criar conta";

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="mx-auto flex w-full max-w-md flex-col gap-4 rounded-2xl border border-line bg-sheet p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-mute">{mode === "login" ? "Use a conta deste estúdio." : "A senha precisa ter pelo menos 8 caracteres."}</p>
      </div>
      <label className="flex flex-col gap-2 text-sm font-semibold">
        E-mail
        <Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label className="flex flex-col gap-2 text-sm font-semibold">
        Senha
        <Input
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={8}
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {error ? (
        <p className="text-sm text-signal" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit">{title}</Button>
      {mode === "login" ? (
        <Link href="/signup" className="text-sm font-semibold text-signal">
          Criar uma conta
        </Link>
      ) : (
        <Link href="/login" className="text-sm font-semibold text-signal">
          Já tenho conta
        </Link>
      )}
    </form>
  );
}
