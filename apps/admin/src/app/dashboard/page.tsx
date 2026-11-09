"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, FileText, ListChecks, UploadCloud } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { Card, ErrorNotice, PageHeader, StatusPill } from "@/components/ui";

type Job = { id: string; job_type: string; status: string; document_title?: string | null };
type ReviewItem = { story: { id: string; title: string }; document: { title: string } | null };

export default function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [queue, setQueue] = useState<ReviewItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<Job[]>("admin/jobs?limit=5"),
      apiRequest<ReviewItem[]>("admin/review-queue?limit=5"),
    ])
      .then(([recentJobs, reviewItems]) => {
        setJobs(recentJobs);
        setQueue(reviewItems);
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Workspace overview"
        title="Good stories begin with careful stewardship."
        description="Monitor source processing, inspect AI-assisted discoveries, and make the human decisions that govern every publication."
        action={<Link className="inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-3 text-sm font-semibold text-white" href="/dashboard/jobs"><UploadCloud size={17} /> Ingest a document</Link>}
      />
      {error && <ErrorNotice message={error} />}
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard icon={<ListChecks size={20} />} label="Awaiting review" value={String(queue.length)} href="/dashboard/review" />
        <SummaryCard icon={<FileText size={20} />} label="Recent processing jobs" value={String(jobs.length)} href="/dashboard/jobs" />
        <SummaryCard icon={<ArrowUpRight size={20} />} label="Rights-first publishing" value="Required" href="/dashboard/review" />
      </div>
      <div className="mt-7 grid gap-5 xl:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Review queue</h2>
            <Link href="/dashboard/review" className="text-sm font-semibold text-forest underline">View queue</Link>
          </div>
          {queue.length === 0 ? <p className="mt-6 text-sm text-slate-500">No stories are waiting for review.</p> : (
            <ul className="mt-4 divide-y divide-slate-100">
              {queue.slice(0, 5).map((item) => <li className="flex items-center justify-between gap-4 py-4" key={item.story.id}>
                <div><p className="font-medium">{item.story.title}</p><p className="mt-1 text-xs text-slate-500">{item.document?.title || "Source document"}</p></div>
                <Link href={`/dashboard/review/${item.story.id}`} className="text-sm font-semibold text-forest">Review</Link>
              </li>)}
            </ul>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Latest jobs</h2>
            <Link href="/dashboard/jobs" className="text-sm font-semibold text-forest underline">View jobs</Link>
          </div>
          {jobs.length === 0 ? <p className="mt-6 text-sm text-slate-500">No processing jobs yet.</p> : (
            <ul className="mt-4 divide-y divide-slate-100">
              {jobs.map((job) => <li className="flex items-center justify-between gap-4 py-4" key={job.id}>
                <div><p className="font-medium capitalize">{job.job_type.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-slate-500">{job.document_title || "Document unavailable"}</p></div>
                <StatusPill value={job.status} />
              </li>)}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

function SummaryCard({ icon, label, value, href }: { icon: React.ReactNode; label: string; value: string; href: string }) {
  return <Link href={href} className="rounded-2xl bg-white p-5 shadow-card transition hover:-translate-y-0.5">
    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sage text-forest">{icon}</span>
    <p className="mt-5 text-sm text-slate-600">{label}</p>
    <p className="mt-1 text-2xl font-semibold capitalize">{value}</p>
  </Link>;
}
