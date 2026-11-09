"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

export default function InvitePage() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/invitations/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: form.get("token"),
          email: form.get("email"),
          password: form.get("password"),
          fullName: form.get("fullName"),
        }),
      });
      const result = await response.json();
      setMessage(response.ok ? "Invitation accepted. You can now sign in." : result.error);
    } catch {
      setMessage("The invitation service could not be reached. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <section className="w-full max-w-lg rounded-3xl bg-white p-8 shadow-card">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-forest">Account invitation</p>
        <h1 className="mt-3 text-3xl font-semibold">Join the curator team</h1>
        <form className="mt-8 space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium">Invitation token<input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="token" required /></label>
          <label className="block text-sm font-medium">Invited email<input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="email" type="email" required autoComplete="email" /></label>
          <label className="block text-sm font-medium">Full name<input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="fullName" required autoComplete="name" /></label>
          <label className="block text-sm font-medium">Create password<input className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3" name="password" type="password" required minLength={10} autoComplete="new-password" /></label>
          {message && <p className="rounded-xl bg-sage/60 p-3 text-sm">{message}</p>}
          <button className="w-full rounded-xl bg-forest px-4 py-3 font-semibold text-white disabled:opacity-60" disabled={busy}>{busy ? "Verifying..." : "Accept invitation"}</button>
        </form>
        <p className="mt-6 text-sm text-slate-600"><Link href="/login" className="font-semibold text-forest underline">Return to sign in</Link></p>
      </section>
    </main>
  );
}
