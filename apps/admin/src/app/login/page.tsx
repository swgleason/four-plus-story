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
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");

  function getSafeNextPath() {
    const next = searchParams.get("next");
    if (!next || !next.startsWith("/") || next.startsWith("//")) return "/dashboard";
    return next;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setErrorMessage("");
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    try {
      const { error } = await createClient().auth.signInWithPassword({
        email,
        password,
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      router.replace(getSafeNextPath());
      router.refresh();
    } catch {
      setErrorMessage("The sign-in service could not be reached. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function sendMagicLink() {
    if (!email.trim()) {
      setErrorMessage("Enter your invited email address to receive a sign-in link.");
      return;
    }
    setBusy(true);
    setErrorMessage("");
    setNotice("");
    try {
      const { error } = await createClient().auth.signInWithOtp({
        email: email.trim(),
        options: {
          shouldCreateUser: false,
          emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(getSafeNextPath())}`,
        },
      });
      if (error) {
        setErrorMessage(error.message);
      } else {
        setNotice("If the email belongs to an invited curator account, a sign-in link has been sent.");
      }
    } catch {
      setErrorMessage("The sign-in service could not be reached. Please try again.");
    } finally {
      setBusy(false);
    }
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
            <input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="password" type="password" required autoComplete="current-password" />
          </label>
          {searchParams.get("error") === "access" && (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This account is not authorized for the curator workbench.</p>
          )}
          {searchParams.get("error") === "callback" && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">That sign-in link is invalid or expired. Request a new one.</p>}
          {searchParams.get("error") === "auth_config" && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Authentication is not configured for this application.</p>}
          {errorMessage && <p className="text-sm text-red-700">{errorMessage}</p>}
          {notice && <p role="status" className="rounded-xl bg-sage/60 p-3 text-sm">{notice}</p>}
          <button className="w-full rounded-xl bg-forest px-4 py-3 font-semibold text-white disabled:opacity-60" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <div className="my-5 flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />OR<span className="h-px flex-1 bg-slate-200" /></div>
        <div className="space-y-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => void sendMagicLink()}
            className="w-full rounded-xl border border-forest px-4 py-3 font-semibold text-forest disabled:opacity-60"
          >
            Email me a sign-in link
          </button>
        </div>
        <p className="mt-6 text-sm text-slate-600">
          Have an invitation token? <Link href="/invite" className="font-semibold text-forest underline">Accept invite</Link>
        </p>
      </section>
    </main>
  );
}
