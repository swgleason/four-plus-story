import { clsx } from "clsx";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-forest">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={clsx("rounded-2xl bg-white p-5 shadow-card md:p-6", className)}>{children}</section>;
}

export function StatusPill({ value }: { value: string }) {
  const color =
    value === "completed" || value === "approved"
      ? "bg-emerald-100 text-emerald-800"
      : value === "failed" || value === "rejected"
        ? "bg-red-100 text-red-800"
        : value === "processing" || value === "under_review"
          ? "bg-amber-100 text-amber-900"
          : "bg-slate-100 text-slate-700";
  return <span className={clsx("inline-flex rounded-full px-3 py-1 text-xs font-semibold capitalize", color)}>{value.replaceAll("_", " ")}</span>;
}

export function ErrorNotice({ message }: { message: string }) {
  return <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{message}</div>;
}

export function LoadingNotice({ children = "Loading..." }: { children?: React.ReactNode }) {
  return <p className="py-8 text-sm text-slate-500">{children}</p>;
}
