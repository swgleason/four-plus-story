"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, BookOpenCheck } from "lucide-react";
import { apiRequest, titleCase } from "@/lib/api";
import { Card, ErrorNotice, LoadingNotice, PageHeader, StatusPill } from "@/components/ui";

type Item = {
  story: {
    id: string;
    title: string;
    original_word_count: number;
    estimated_spoken_duration_seconds: number;
    length_advisory_exceeds_600_words: boolean;
    narrator_gender?: string;
  };
  document: { title: string; author: string | null; rights_status: string; publication_restrictions: string | null } | null;
  evaluation: { overall_classification: string; overall_confidence: number } | null;
  variants: { variant: string }[];
};

export default function ReviewQueuePage() {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiRequest<Item[]>("admin/review-queue?limit=200")
      .then(setItems)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, []);

  return <>
    <PageHeader eyebrow="Editorial review" title="Story review queue" description="Review exact source text and evidence before deciding whether a story can be approved or published." />
    {error && <ErrorNotice message={error} />}
    {loading ? <LoadingNotice /> : items.length === 0 ? <Card><div className="flex items-center gap-3"><BookOpenCheck className="text-forest" /><div><h2 className="font-semibold">Queue is clear</h2><p className="mt-1 text-sm text-slate-500">No discovered stories are awaiting review.</p></div></div></Card> : (
      <div className="grid gap-4 lg:grid-cols-2">{items.map((item) => <Card key={item.story.id}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 className="text-lg font-semibold">{item.story.title}</h2><p className="mt-1 text-sm text-slate-500">{item.document?.title || "Unknown source"}{item.document?.author ? ` · ${item.document.author}` : ""}</p></div>
          <StatusPill value={item.story.narrator_gender || "unknown"} />
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
          <Metric label="Original words" value={String(item.story.original_word_count)} />
          <Metric label="Spoken time" value={`${Math.ceil(item.story.estimated_spoken_duration_seconds / 60)} min`} />
          <Metric label="Evaluation" value={item.evaluation ? `${Math.round(item.evaluation.overall_confidence * 100)}%` : "Pending"} />
        </div>
        {item.story.length_advisory_exceeds_600_words && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Long story advisory: original exceeds 600 words.</p>}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500">Rights</span><StatusPill value={item.document?.rights_status || "unknown"} />
          {item.evaluation && <span className="ml-auto text-xs text-slate-600">{titleCase(item.evaluation.overall_classification)}</span>}
        </div>
        {item.variants.length > 0 && <p className="mt-3 text-xs text-slate-600">Proposed variants: {item.variants.map((variant) => titleCase(variant.variant)).join(", ")}</p>}
        <Link href={`/dashboard/review/${item.story.id}`} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-3 text-sm font-semibold text-white">Open review <ArrowRight size={16} /></Link>
      </Card>)}</div>
    )}
  </>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-sand p-3"><p className="text-[11px] text-slate-500">{label}</p><p className="mt-1 font-semibold">{value}</p></div>;
}
