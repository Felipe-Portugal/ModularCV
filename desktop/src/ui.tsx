import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { failureText, useApp } from "./ctx";
import type { AdapterFailure, FactStatus, Problem, Visibility } from "./types";

const TONES = {
  success: "border-success/40 bg-successbg text-success",
  warning: "border-warning/40 bg-warningbg text-warning",
  danger: "border-danger/40 bg-dangerbg text-danger",
  neutral: "border-line bg-surface2 text-ink2",
} as const;

export function Pill({ tone = "neutral", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={"inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium " + TONES[tone]}>{children}</span>;
}

export function StatusPill({ status }: { status: FactStatus }) {
  const { m } = useApp();
  const tone = status === "CONFIRMED" ? "success" : status === "WITHDRAWN" ? "danger" : "warning";
  return (
    <span title={m.facts.statusHelp[status]}>
      <Pill tone={tone}>{m.facts.statusLabels[status] ?? status}</Pill>
    </span>
  );
}

export function VisibilityPill({ visibility }: { visibility: Visibility }) {
  const { m } = useApp();
  return visibility === "public" ? <Pill tone="success">{m.common.public}</Pill> : <Pill>{m.common.private}</Pill>;
}

export function Notice({ tone, title, children }: { tone: "success" | "warning" | "danger" | "neutral"; title?: string; children?: ReactNode }) {
  return (
    <div role={tone === "danger" || tone === "warning" ? "alert" : "status"} className={"rise rounded-xl border p-4 " + TONES[tone]}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className="mt-1 text-sm leading-relaxed text-ink">{children}</div>}
    </div>
  );
}

export function ProblemList({ items }: { items: Problem[] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-2 space-y-1.5">
      {items.slice(0, 12).map((p, i) => (
        <li key={i} className="text-sm">
          {p.file && <span className="mr-1 rounded bg-surface2 px-1.5 py-0.5 text-[10px] uppercase text-ink2">{p.file}</span>}
          <code className="font-mono text-xs">{p.code}</code>
          {p.path && <span className="text-xs text-ink2"> · {p.path}</span>}
          <span className="block text-ink2">{p.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function FailureNotice({ failure }: { failure: AdapterFailure }) {
  const { m } = useApp();
  const friendly = m.errors[failure.code] ?? m.jobErrors[failure.code] ?? m.pkgErrors[failure.code];
  return (
    <Notice tone={["CONFLICT", "CONFIRMATION_REQUIRED", "OUTPUT_EXISTS", "OFFER_EXISTS", "BUSY", "PACKAGE_EXISTS", "PROVENANCE_REFUSED", "PDF_UNAVAILABLE"].includes(failure.code) ? "warning" : "danger"} title={failureText(m, failure.code, failure.message)}>
      {friendly && failure.message !== friendly && <span className="text-ink2">{failure.message}</span>}
      <ProblemList items={failure.details} />
    </Notice>
  );
}

export function Card({ title, aside, children }: { title?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
      {(title || aside) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="font-display text-lg font-semibold">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export const inputCls =
  "mt-1.5 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none placeholder:text-ink2/60 focus:border-accent disabled:opacity-60";

export function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-ink2">{hint}</p>}
    </div>
  );
}

export function Button({ variant = "secondary", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const base = "cursor-pointer rounded-lg px-3.5 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ";
  const style =
    variant === "primary"
      ? "bg-accent font-medium text-accentink hover:opacity-90"
      : variant === "danger"
        ? "bg-danger font-medium text-bg hover:opacity-90"
        : variant === "ghost"
          ? "text-ink2 hover:bg-surface2 hover:text-ink"
          : "border border-line hover:bg-surface2";
  return <button type="button" {...props} className={base + style + " " + (props.className ?? "")} />;
}

export function VisibilityToggle({ name, value, onChange }: { name: string; value: Visibility; onChange: (v: Visibility) => void }) {
  const { m } = useApp();
  return (
    <fieldset className="mt-1.5 flex gap-1 rounded-lg border border-line p-0.5">
      <legend className="sr-only">{m.profile.visibilityLabel}</legend>
      {(["public", "private"] as const).map((v) => (
        <label
          key={v}
          title={v === "public" ? m.profile.publicHelp : m.profile.privateHelp}
          className={"cursor-pointer rounded-md px-2.5 py-1.5 text-xs has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent " + (value === v ? "bg-surface2 font-medium text-ink" : "text-ink2 hover:text-ink")}
        >
          <input type="radio" className="sr-only" name={name} value={v} checked={value === v} onChange={() => onChange(v)} />
          {v === "public" ? m.common.public : m.common.private}
        </label>
      ))}
    </fieldset>
  );
}

/** Modal alert dialog with Escape and initial focus on the safe action. */
export function ConfirmDialog({ title, body, confirmLabel, cancelLabel, onConfirm, onCancel }: { title: string; body: string; confirmLabel: string; cancelLabel: string; onConfirm: () => void; onCancel: () => void }) {
  const stay = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    stay.current?.focus();
    const on = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onCancel]);
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4">
      <div role="alertdialog" aria-modal="true" aria-labelledby="dlg-title" aria-describedby="dlg-body" className="rise w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl">
        <h2 id="dlg-title" className="font-display text-lg font-semibold">{title}</h2>
        <p id="dlg-body" className="mt-2 text-sm leading-relaxed text-ink2">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button ref={stay} type="button" onClick={onCancel} className="cursor-pointer rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-accentink hover:opacity-90">
            {cancelLabel}
          </button>
          <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
