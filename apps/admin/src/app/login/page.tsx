"use client";

import Link from "next/link";
import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-sand" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [errorMessage, setErrorMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setErrorMessage("");
    const form = new FormData(event.currentTarget);
    const { error } = await createClient().auth.signInWithPassword({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    setBusy(false);
    if (error) {
      setErrorMessage(error.message);
      return;
    }
    router.replace(searchParams.get("next") || "/dashboard");
    router.refresh();
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <section className="w-full max-w-md rounded-3xl bg-white p-8 shadow-card">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-forest">Four Plus Story</p>
        <h1 className="mt-3 text-3xl font-semibold">Curator sign in</h1>
        <p className="mt-2 text-sm text-slate-600">Sign in with your invited curator account.</p>
        <form className="mt-8 space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium">
            Email
            <input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="email" type="email" required autoComplete="email" />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="password" type="password" required autoComplete="current-password" />
          </label>
          {searchParams.get("error") === "access" && (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This account is not authorized for the curator workbench.</p>
          )}
          {errorMessage && <p className="text-sm text-red-700">{errorMessage}</p>}
          <button className="w-full rounded-xl bg-forest px-4 py-3 font-semibold text-white disabled:opacity-60" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-sm text-slate-600">
          Have an invitation token? <Link href="/invite" className="font-semibold text-forest underline">Accept invite</Link>
        </p>
      </section>
    </main>
  );
}
