"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Brain, CheckCircle2, HeartPulse, Save, Sparkles } from "lucide-react";
import { apiRequest, titleCase } from "@/lib/api";
import { Card, ErrorNotice, LoadingNotice, PageHeader, StatusPill } from "@/components/ui";

type Span = { id: string; span_order: number; page_number: number; char_start: number; char_end: number; verbatim_text: string };
type Criterion = { result: string; confidence: number; evidence_quote: string; reasoning: string; intensity_level?: string; emotions_identified?: string[]; sensations_identified?: string[]; sensations_missing?: boolean; coregulator_type?: string };
type Evaluation = { overall_classification: string; overall_confidence: number; criteria_evaluations: Record<string, Criterion>; reasoning_summary: string };
type CuratedVersion = { id: string; curated_title: string; curated_text: string; editorial_notes: string | null; curated_word_count: number; is_approved: boolean };
type ReviewData = {
  story: { id: string; title: string; original_text: string; original_word_count: number; estimated_spoken_duration_seconds: number; length_advisory_exceeds_600_words: boolean; narrator_gender: string; status: string };
  document: { title: string; author: string | null; rights_status: string; publication_restrictions: string | null } | null;
  spans: Span[];
  evaluation: Evaluation | null;
  variants: { variant: string; confidence: number; evidence_quote: string; reasoning: string }[];
  emotions: { emotion: string; energy_level: string; progression_stage: string; evidence_quote: string; sensations_identified: string[]; sensations_missing: boolean }[];
  step_analysis: { setting: string; trigger: string; emotion_and_body_sensations: string; point: string } | null;
  curated_versions: CuratedVersion[];
};

const clearedRights = new Set(["public_domain", "licensed", "fair_use_educational"]);
const visibilityOptions = ["internal_only", "registered_users", "public"];

export default function StoryReviewPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const router = useRouter();
  const [data, setData] = useState<ReviewData | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [visibility, setVisibility] = useState("registered_users");
  const [draftId, setDraftId] = useState<string | undefined>();
  const [curatedTitle, setCuratedTitle] = useState("");
  const [curatedText, setCuratedText] = useState("");
  const [editorialNotes, setEditorialNotes] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await apiRequest<ReviewData>(`admin/stories/${storyId}`);
      setData(result);
      const draft = result.curated_versions.find((version) => !version.is_approved);
      if (draft) {
        setDraftId(draft.id);
        setCuratedTitle(draft.curated_title);
        setCuratedText(draft.curated_text);
        setEditorialNotes(draft.editorial_notes || "");
      } else {
        setCuratedTitle(result.story.title);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }, [storyId]);

  useEffect(() => { void load(); }, [load]);

  const wordCount = useMemo(() => curatedText.trim() ? curatedText.trim().split(/\s+/).length : 0, [curatedText]);
  const spokenSeconds = Math.ceil(wordCount * 60 / 140);
  const canPublish = Boolean(
    data?.document &&
    clearedRights.has(data.document.rights_status) &&
    !data.document.publication_restrictions,
  );
  const criteria = data?.evaluation?.criteria_evaluations || {};

  async function saveDraft() {
    if (!data) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await apiRequest<CuratedVersion>(`admin/stories/${storyId}/curated`, {
        method: "POST",
        body: JSON.stringify({
          curated_title: curatedTitle,
          curated_text: curatedText,
          editorial_notes: editorialNotes || null,
          version_id: draftId,
        }),
      });
      setDraftId(saved.id);
      setNotice(`Curated draft saved · ${saved.curated_word_count} words · ${Math.ceil(saved.curated_word_count * 60 / 140)} sec.`);
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function triggerEvaluation() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiRequest(`stories/${storyId}/evaluate`, { method: "POST" });
      setNotice("AI evaluation queued. Track progress in the ingestion & jobs dashboard.");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "approve" | "reject" | "request_revision") {
    if (!data) return;
    if (action === "approve" && visibility !== "internal_only" && !canPublish) {
      setError("Publication is blocked until document rights are cleared and restrictions removed.");
      return;
    }
    const confirmed = action !== "approve" || window.confirm(
      `Approve this story with ${titleCase(visibility)} visibility? Original source text will remain unchanged.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiRequest(`admin/stories/${storyId}/review`, {
        method: "POST",
        body: JSON.stringify({
          action,
          visibility,
          notes: action === "approve" ? "Approved from curator workbench." : null,
        }),
      });
      setNotice(action === "approve" ? "Story approved. Publication visibility has been recorded." : `Story ${action.replace("_", " ")} recorded.`);
      router.push("/dashboard/review");
    } catch (cause) {
      setError((cause as Error).message);
      setBusy(false);
    }
  }

  if (loading) return <LoadingNotice>Loading story source and evaluation…</LoadingNotice>;
  if (!data) return <ErrorNotice message={error || "Story not found."} />;
  const rightsCleared = canPublish;

  return <>
    <Link href="/dashboard/review" className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-forest"><ArrowLeft size={16} /> Back to review queue</Link>
    <PageHeader eyebrow="Story review" title={data.story.title} description={`${data.document?.title || "Unknown source"}${data.document?.author ? ` · ${data.document.author}` : ""}`} action={<StatusPill value={data.story.status} />} />
    {error && <ErrorNotice message={error} />}
    {notice && <p role="status" className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">{notice}</p>}

    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.8fr)]">
      <div className="space-y-5">
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-forest">Immutable original</p><h2 className="mt-2 text-xl font-semibold">Source narrative</h2></div>
            <div className="flex gap-2"><StatusPill value={data.story.narrator_gender || "unknown"} /><StatusPill value={data.document?.rights_status || "unknown"} /></div>
          </div>
          <div className="mt-5 max-h-[34rem] overflow-auto whitespace-pre-wrap rounded-xl bg-sand p-5 text-sm leading-7">{data.story.original_text}</div>
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-600">
            <span>{data.story.original_word_count} original words</span>
            <span>~{Math.ceil(data.story.estimated_spoken_duration_seconds / 60)} min spoken</span>
            <span>Gender: {data.story.narrator_gender || "unknown"}</span>
          </div>
          {data.story.length_advisory_exceeds_600_words && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Length advisory: this source story exceeds 600 words.</p>}
        </Card>

        <Card>
          <div className="flex items-center justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-forest">Verified boundaries</p><h2 className="mt-2 text-xl font-semibold">Source spans</h2></div><span className="text-sm text-slate-500">{data.spans.length} spans</span></div>
          {data.spans.length ? <ol className="mt-5 space-y-3">{data.spans.map((span) => <li className="rounded-xl border border-slate-100 p-4" key={span.id}>
            <div className="mb-2 flex flex-wrap justify-between gap-2 text-xs font-semibold text-slate-500"><span>Span {span.span_order} · Page {span.page_number}</span><span>Characters {span.char_start}–{span.char_end}</span></div>
            <p className="whitespace-pre-wrap text-sm leading-6">{span.verbatim_text}</p>
          </li>)}</ol> : <p className="mt-4 text-sm text-slate-500">No verified source spans have been attached.</p>}
        </Card>

        <Card>
          <div className="flex items-start justify-between gap-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-forest">AI proposal · human review required</p><h2 className="mt-2 text-xl font-semibold">5-way criteria</h2></div>
            {!data.evaluation && <button onClick={() => void triggerEvaluation()} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-forest px-3 py-2 text-sm font-semibold text-forest disabled:opacity-50"><Sparkles size={15} /> Run evaluation</button>}
          </div>
          {data.evaluation ? <>
            <div className="mt-4 flex flex-wrap gap-3"><StatusPill value={data.evaluation.overall_classification} /><span className="rounded-full bg-sage px-3 py-1 text-xs font-semibold">{Math.round(data.evaluation.overall_confidence * 100)}% confidence</span></div>
            <div className="mt-4 space-y-3">{Object.entries(criteria).map(([name, criterion]) => <div key={name} className="rounded-xl border border-slate-100 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{titleCase(name)}</h3><div className="flex gap-2"><StatusPill value={criterion.result} /><span className="text-xs text-slate-500">{Math.round(criterion.confidence * 100)}%</span></div></div>
              {criterion.evidence_quote && <blockquote className="mt-3 border-l-2 border-forest pl-3 text-sm italic text-slate-700">“{criterion.evidence_quote}”</blockquote>}
              <p className="mt-2 text-sm leading-6 text-slate-600">{criterion.reasoning}</p>
              {criterion.sensations_missing && <p className="mt-2 text-xs font-medium text-amber-800">Somatic sensations not stated in the source.</p>}
              {!!criterion.sensations_identified?.length && <p className="mt-2 text-xs text-slate-600">Explicit sensations: {criterion.sensations_identified.join(", ")}</p>}
            </div>)}</div>
            <p className="mt-4 text-sm leading-6 text-slate-600">{data.evaluation.reasoning_summary}</p>
          </> : <p className="mt-5 text-sm text-slate-500">No evaluation available yet. AI output is a proposal and never grants approval.</p>}
        </Card>

        <Card>
          <div className="flex items-center gap-2"><HeartPulse className="text-forest" size={19} /><h2 className="text-xl font-semibold">Emotion & somatic evidence</h2></div>
          {data.emotions.length ? <div className="mt-4 space-y-3">{data.emotions.map((emotion, index) => <div key={`${emotion.emotion}-${index}`} className="rounded-xl bg-sand p-4">
            <div className="flex flex-wrap items-center gap-2"><StatusPill value={emotion.emotion} /><span className="text-xs capitalize text-slate-600">{titleCase(emotion.energy_level)} · {titleCase(emotion.progression_stage)}</span></div>
            <p className="mt-3 text-sm italic">“{emotion.evidence_quote}”</p>
            <p className="mt-2 text-sm text-slate-600">Somatic sensations: {emotion.sensations_identified.length ? emotion.sensations_identified.join(", ") : "None explicitly stated"}</p>
          </div>)}</div> : <p className="mt-4 text-sm text-slate-500">No emotion classifications are recorded.</p>}
        </Card>

        <Card>
          <div className="flex items-center gap-2"><Brain className="text-forest" size={19} /><h2 className="text-xl font-semibold">Restored STEP analysis</h2></div>
          {data.step_analysis ? <div className="mt-4 grid gap-3 md:grid-cols-2">{[
            ["S · Setting", data.step_analysis.setting],
            ["T · Trigger", data.step_analysis.trigger],
            ["E · Emotion & body sensations", data.step_analysis.emotion_and_body_sensations],
            ["P · Point", data.step_analysis.point],
          ].map(([label, value]) => <div key={label} className="rounded-xl bg-sand p-4"><h3 className="text-sm font-semibold">{label}</h3><p className="mt-2 text-sm leading-6 text-slate-700">{value}</p></div>)}</div> : <p className="mt-4 text-sm text-slate-500">STEP analysis is not available.</p>}
          {!!data.variants.length && <div className="mt-5"><h3 className="text-sm font-semibold">Proposed authoritative variants</h3><div className="mt-2 space-y-2">{data.variants.map((variant) => <div className="rounded-lg border border-slate-100 p-3" key={variant.variant}><div className="flex justify-between gap-2 text-sm font-medium"><span>{titleCase(variant.variant)}</span><span>{Math.round(variant.confidence * 100)}%</span></div><p className="mt-2 text-xs italic text-slate-600">“{variant.evidence_quote}”</p><p className="mt-2 text-xs text-slate-600">{variant.reasoning}</p></div>)}</div></div>}
        </Card>
      </div>

      <div className="space-y-5 xl:sticky xl:top-6">
        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-forest">Human-edited version</p>
          <h2 className="mt-2 text-xl font-semibold">Curated telling</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">Edit separately from the verbatim source. Saving creates an unapproved draft.</p>
          <label className="mt-5 block text-sm font-medium">Curated title<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5" value={curatedTitle} onChange={(event) => setCuratedTitle(event.target.value)} maxLength={500} /></label>
          <label className="mt-4 block text-sm font-medium">Curated text<textarea className="mt-1 min-h-64 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm leading-6" value={curatedText} onChange={(event) => setCuratedText(event.target.value)} /></label>
          <div className="mt-3 flex flex-wrap justify-between gap-2 rounded-xl bg-sand p-3 text-sm"><span>{wordCount} words</span><span>~{Math.ceil(spokenSeconds / 60)} min ({spokenSeconds} sec) at 140 wpm</span></div>
          {wordCount > 600 && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Length advisory: curated telling exceeds 600 words.</p>}
          <label className="mt-4 block text-sm font-medium">Editorial notes<textarea className="mt-1 min-h-20 w-full rounded-xl border border-slate-200 px-3 py-2.5" value={editorialNotes} onChange={(event) => setEditorialNotes(event.target.value)} /></label>
          <button onClick={() => void saveDraft()} disabled={busy || wordCount === 0 || !curatedTitle.trim()} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-forest px-4 py-3 text-sm font-semibold text-forest disabled:opacity-50"><Save size={16} /> Save draft</button>
        </Card>

        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-forest">Publication decision</p>
          <h2 className="mt-2 text-xl font-semibold">Approve & set visibility</h2>
          <div className="mt-4 rounded-xl bg-sand p-4 text-sm">
            <p className="font-semibold">Document rights: {titleCase(data.document?.rights_status || "unknown")}</p>
            <p className="mt-1 text-slate-600">{data.document?.publication_restrictions ? `Restriction: ${data.document.publication_restrictions}` : "No recorded publication restriction."}</p>
          </div>
          {!rightsCleared && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-5 text-amber-900">Public or registered publication is blocked until rights are cleared and restrictions are removed.</p>}
          <label className="mt-4 block text-sm font-medium">Visibility tier<select className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5" value={visibility} onChange={(event) => setVisibility(event.target.value)}>{visibilityOptions.map((option) => <option value={option} key={option}>{titleCase(option)}</option>)}</select></label>
          <button onClick={() => void review("approve")} disabled={busy || (visibility !== "internal_only" && !rightsCleared)} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-forest px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"><CheckCircle2 size={17} /> Approve story</button>
          <div className="mt-3 grid grid-cols-2 gap-3"><button onClick={() => void review("request_revision")} disabled={busy} className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold">Request revision</button><button onClick={() => void review("reject")} disabled={busy} className="rounded-xl border border-red-200 px-3 py-2.5 text-sm font-semibold text-red-700">Reject</button></div>
          <p className="mt-4 text-xs leading-5 text-slate-500">AI discoveries remain private until a human approves them. Rights clearance gates public and registered visibility; the original story text is never edited here.</p>
        </Card>
      </div>
    </div>
  </>;
}
