"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { RefreshCw, UploadCloud } from "lucide-react";
import { apiRequest, formatDate, titleCase } from "@/lib/api";
import { Card, ErrorNotice, LoadingNotice, PageHeader, StatusPill } from "@/components/ui";

type JobEvent = { id: string; stage: string; level: string; message: string; created_at: string };
type Job = {
  id: string;
  document_id: string | null;
  document_title: string | null;
  job_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
  events: JobEvent[];
};

const documentTypes = ["pdf_book", "pdf_article", "txt_transcript", "txt_story_note"];
const rightsTypes = ["restricted_internal", "fair_use_educational", "licensed", "public_domain"];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadJobs = useCallback(async () => {
    setError("");
    try {
      setJobs(await apiRequest<Job[]>("admin/jobs?limit=100"));
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
    const timer = window.setInterval(() => void loadJobs(), 15000);
    return () => window.clearInterval(timer);
  }, [loadJobs]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const body = new FormData(event.currentTarget);
      const result = await apiRequest<{ document: { title: string }; job: Job }>(
        "documents/upload",
        { method: "POST", body },
      );
      setNotice(`“${result.document.title}” uploaded. Its processing job is queued.`);
      formElement.reset();
      await loadJobs();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function scan(documentId: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiRequest(`documents/${documentId}/scan`, { method: "POST" });
      setNotice("Story boundary scan queued.");
      await loadJobs();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Document operations" title="Ingestion & processing" description="Upload source documents, follow extraction and discovery jobs, and inspect their event logs." action={<button onClick={() => void loadJobs()} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold"><RefreshCw size={16} /> Refresh</button>} />
      {error && <ErrorNotice message={error} />}
      {notice && <p role="status" className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">{notice}</p>}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.4fr)]">
        <Card>
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sage text-forest"><UploadCloud size={19} /></span>
            <div><h2 className="font-semibold">Upload a source</h2><p className="text-xs text-slate-500">PDF and UTF-8 text supported</p></div>
          </div>
          <form onSubmit={upload} className="mt-6 space-y-4">
            <label className="block text-sm font-medium">Title<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5" name="title" required maxLength={500} /></label>
            <label className="block text-sm font-medium">Author / speaker<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5" name="author" maxLength={500} /></label>
            <label className="block text-sm font-medium">Document type<select className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5" name="document_type">{documentTypes.map((type) => <option value={type} key={type}>{titleCase(type)}</option>)}</select></label>
            <label className="block text-sm font-medium">Source URL <span className="font-normal text-slate-500">(optional)</span><input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5" name="source_url" type="url" placeholder="https://..." /></label>
            <label className="block text-sm font-medium">Rights status<select className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5" name="rights_status">{rightsTypes.map((right) => <option value={right} key={right}>{titleCase(right)}</option>)}</select></label>
            <label className="block text-sm font-medium">Source file<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 file:mr-3 file:rounded-lg file:border-0 file:bg-sage file:px-3 file:py-2" name="file" type="file" accept=".pdf,.txt,application/pdf,text/plain" required /></label>
            <p className="text-xs leading-5 text-slate-500">Sources default to restricted rights. Confirm the document’s license and any publication restrictions before selecting a broader rights status.</p>
            <button disabled={busy} className="w-full rounded-xl bg-forest px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Working..." : "Upload & process"}</button>
          </form>
        </Card>
        <section>
          <div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">Processing jobs</h2><span className="text-xs text-slate-500">Refreshes every 15 seconds</span></div>
          {loading ? <LoadingNotice /> : jobs.length === 0 ? <Card><p className="text-sm text-slate-500">No jobs yet. Upload a document to begin.</p></Card> : (
            <div className="space-y-4">{jobs.map((job) => (
              <Card key={job.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><p className="font-semibold">{job.document_title || "Document job"}</p><p className="mt-1 text-xs capitalize text-slate-500">{titleCase(job.job_type)} · {formatDate(job.created_at)}</p></div>
                  <StatusPill value={job.status} />
                </div>
                {job.error_message && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{job.error_message}</p>}
                <details className="mt-4">
                  <summary className="cursor-pointer text-sm font-semibold text-forest">Processing events ({job.events.length})</summary>
                  {job.events.length === 0 ? <p className="py-3 text-sm text-slate-500">No events recorded.</p> : (
                    <ol className="mt-3 space-y-3 border-l border-slate-200 pl-4">{job.events.map((event) => <li key={event.id} className="relative text-sm before:absolute before:-left-[21px] before:top-1.5 before:h-2 before:w-2 before:rounded-full before:bg-forest">
                      <p className="font-medium">{event.message}</p><p className="mt-1 text-xs text-slate-500">{titleCase(event.stage)} · {event.level} · {formatDate(event.created_at)}</p>
                    </li>)}</ol>
                  )}
                </details>
                {job.document_id && job.status === "completed" && job.job_type !== "story_discovery" && (
                  <button disabled={busy} onClick={() => void scan(job.document_id!)} className="mt-4 rounded-lg border border-forest px-3 py-2 text-sm font-semibold text-forest disabled:opacity-50">Scan for story candidates</button>
                )}
              </Card>
            ))}</div>
          )}
        </section>
      </div>
    </>
  );
}
