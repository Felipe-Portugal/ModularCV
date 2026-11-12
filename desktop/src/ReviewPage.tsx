import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { adapter } from "./bridge";
import { useApp } from "./ctx";
import { SELECTED_PACKAGE_KEY, approveCommand, confirmationPrefix, explain, formatBytes, verdictTone } from "./packages";
import { Button, Card, ConfirmDialog, FailureNotice, Notice, Pill, inputCls } from "./ui";
import type { ViewerInfo } from "./PdfViewer";
import type { AdapterFailure, ApprovalDone, PackageReview, PackagesList } from "./types";

const PdfViewer = lazy(() => import("./PdfViewer"));

function remembered(): string {
  try {
    return localStorage.getItem(SELECTED_PACKAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function remember(name: string) {
  try {
    localStorage.setItem(SELECTED_PACKAGE_KEY, name);
  } catch {
    /* optional convenience */
  }
}

/** Reasons that do not prevent a person from approving: the engine's own accepted set (see `package.record_review`). */
const REVIEW_ONLY = ["HUMAN_REVIEW_REQUIRED"];

export default function ReviewPage() {
  const { m, lang, workspace, navigate } = useApp();
  const t = m.review;
  const [list, setList] = useState<PackagesList | null>(null);
  const [name, setName] = useState(remembered);
  const [review, setReview] = useState<PackageReview | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [computedAt, setComputedAt] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);
  const [outcome, setOutcome] = useState<ApprovalDone | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const res = await adapter<PackagesList>(workspace, "packages_list", {});
      if (cancelled) return;
      if (!res.ok) return setFailure(res);
      setList(res);
      setName((current) => (res.packages.some((p) => p.name === current) ? current : (res.packages[0]?.name ?? "")));
    })();
    return () => {
      cancelled = true;
    };
  }, [workspace]);

  const load = useCallback(async () => {
    if (!name) return setReview(null);
    setBusy(true);
    setFailure(null);
    const res = await adapter<PackageReview>(workspace, "package_review", { name });
    setBusy(false);
    if (!res.ok) {
      setReview(null);
      return setFailure(res);
    }
    setReview(res);
    setComputedAt(new Date());
    setTick((n) => n + 1);
  }, [workspace, name]);

  // The verdict is recomputed by the engine every time a package is opened and on demand: never cached.
  useEffect(() => {
    if (name) remember(name);
    setOutcome(null);
    void load();
  }, [load, name]);

  if (list && list.packages.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-line p-10 text-center">
        <p className="font-display text-lg font-semibold">{t.none}</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink2">{t.noneBody}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="primary" onClick={() => navigate("adapt")}>{t.goAdapt}</Button>
          <Button onClick={() => navigate("history")}>{t.goHistory}</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{t.intro}</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 sm:max-w-sm">
          <label htmlFor="rv-package" className="block text-sm font-medium">{t.choose}</label>
          <select
            id="rv-package"
            className="mt-1.5 w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
            value={name}
            onChange={(e) => setName(e.target.value)}
          >
            {(list?.packages ?? []).map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </div>
        <Button onClick={() => { setOutcome(null); void load(); }} disabled={busy || !name}>{busy ? t.refreshing : t.refresh}</Button>
        {computedAt && !busy && <p className="text-xs text-ink2">{t.computedAt.replace("{time}", computedAt.toLocaleTimeString(lang === "fr" ? "fr-FR" : "en-GB"))}</p>}
      </div>

      {failure && (
        <Notice tone="danger" title={t.unreadableTitle}>
          <FailureNotice failure={failure} />
        </Notice>
      )}
      {!review && !failure && <p role="status" className="text-sm text-ink2">{m.workspace.loading}</p>}
      {review && <ReviewBody review={review} workspace={workspace} refreshKey={tick} outcome={outcome} onDecided={(o) => { setOutcome(o); void load(); }} onReload={() => { setOutcome(null); void load(); }} />}
    </div>
  );
}

function ReviewBody({ review, workspace, refreshKey, outcome, onDecided, onReload }: { review: PackageReview; workspace: string; refreshKey: number; outcome: ApprovalDone | null; onDecided: (o: ApprovalDone) => void; onReload: () => void }) {
  const { m } = useApp();
  const t = m.review;
  const s = review.summary;
  const state = review.status;
  const tone = verdictTone(state.status);
  const known = state.status in t.verdict;
  const doc = s.document;
  const ack = s.to_acknowledge;
  const blocking = state.reasons.filter((r) => !REVIEW_ONLY.includes(r));
  const command = approveCommand(workspace, s.package);
  const [copied, setCopied] = useState(false);
  const [viewer, setViewer] = useState<ViewerInfo | null>(null);
  const [seen, setSeen] = useState<number[]>([]);
  useEffect(() => setSeen([]), [refreshKey]);
  const reviewable = state.status === "NEEDS_REVIEW" && state.reasons.length > 0 && state.reasons.every((r) => REVIEW_ONLY.includes(r)) && !!doc.sha256;
  const detailFor = (reason: string) => review.status.details.filter((d) => d.reason === reason || d.code === reason);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* the command stays selectable */
    }
  }

  return (
    <div className="space-y-6">
      {outcome && (
        <Notice tone={outcome.status.status === "READY_TO_SEND" ? "success" : "warning"} title={outcome.decision === "APPROVED" ? m.approve.doneApproved : m.approve.doneRejected}>
          {m.approve.engineSays} <strong>{m.review.verdict[outcome.status.status] ?? outcome.status.status}</strong> <code className="font-mono text-xs">{outcome.status.status}</code>
          {outcome.status.status !== "READY_TO_SEND" && outcome.decision === "APPROVED" && <span className="mt-1 block">{m.approve.notReadyAfter}</span>}
        </Notice>
      )}

      {/* ---- status: computed by the engine, shown with its reasons */}
      <section aria-labelledby="rv-status" className={"rise rounded-2xl border p-5 " + (tone === "success" ? "border-success/40 bg-successbg" : tone === "warning" ? "border-warning/40 bg-warningbg" : tone === "danger" ? "border-danger/40 bg-dangerbg" : "border-line bg-surface2")}>
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="rv-status" className="font-display text-xl font-semibold">{t.statusTitle}</h2>
          <Pill tone={tone}>{t.verdict[state.status] ?? state.status}</Pill>
          <code className="font-mono text-xs text-ink2">{state.status}</code>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-ink">{known ? t.verdictBody[state.status] : t.unknownVerdict}</p>
        {state.status === "READY_TO_SEND" && <p className="mt-1 text-xs text-ink2">{t.readyNote}</p>}
        <h3 className="mt-4 text-sm font-medium">{t.reasons}</h3>
        {state.reasons.length === 0 ? (
          <p className="mt-1 text-sm text-ink2">—</p>
        ) : (
          <ul className="mt-1.5 space-y-2">
            {state.reasons.map((r) => (
              <li key={r} className="text-sm">
                <code className="font-mono text-xs">{r}</code>
                <p className="text-ink">{explain(t.reasonText, r, r)}</p>
                {detailFor(r).slice(0, 2).map((d, i) => (
                  <p key={i} className="text-xs text-ink2">{t.engineMessage}: <code className="font-mono">{d.code}</code> {d.message}</p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ---- the exact document */}
      <Card title={t.document}>
        <dl className="mb-4 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
          <dt className="text-ink2">{t.family}</dt>
          <dd><Pill>{s.family}</Pill></dd>
          <dt className="text-ink2">{t.language}</dt>
          <dd><Pill>{s.language}</Pill></dd>
          <dt className="text-ink2">{t.pagination}</dt>
          <dd className="flex flex-wrap items-center gap-2">
            <span className="tabular-nums">{(doc.page_target == null ? t.noTarget : t.pagesOf).replace("{pages}", String(doc.pages ?? "?")).replace("{target}", String(doc.page_target ?? ""))}</span>
            <Pill tone={doc.page_verdict === "TARGET_EXCEEDED" ? "warning" : doc.page_verdict === "TARGET_MET" ? "success" : "neutral"}>{t.pageVerdict[doc.page_verdict] ?? doc.page_verdict}</Pill>
          </dd>
          <dt className="text-ink2">{t.origin}</dt>
          <dd>
            {doc.origin === "COMPILED_FROM_VERIFIED_TEX" ? <span>{t.originOk}</span> : <span className="text-warning">{t.originNo}</span>}
            <code className="ml-2 font-mono text-xs text-ink2">{doc.origin ?? "—"}</code>
          </dd>
          <dt className="text-ink2">{m.preview.size}</dt>
          <dd className="tabular-nums">{formatBytes(doc.bytes)}</dd>
        </dl>
        <Suspense fallback={<p role="status" className="text-sm text-ink2">{m.preview.loading}</p>}>
          <PdfViewer target={{ package: s.package }} exact="package" refreshKey={refreshKey} onLoaded={setViewer} onPageShown={(p) => setSeen((cur) => (cur.includes(p) ? cur : [...cur, p]))} />
        </Suspense>
      </Card>

      {/* ---- what must be examined */}
      <Card title={t.toExamine}>
        <div className="space-y-5">
          <section>
            <h3 className="text-sm font-medium">{t.unsatisfied} <span className="tabular-nums text-ink2">({ack.unsatisfied_required.length})</span></h3>
            {ack.unsatisfied_required.length === 0 ? (
              <p className="mt-1 text-sm text-ink2">{t.unsatisfiedNone}</p>
            ) : (
              <>
                <p className="mt-1 text-sm text-ink2">{t.unsatisfiedBody}</p>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {ack.unsatisfied_required.map((id) => <li key={id}><Pill tone="warning">{id}</Pill></li>)}
                </ul>
              </>
            )}
          </section>
          <section>
            <h3 className="text-sm font-medium">{t.directives} <span className="tabular-nums text-ink2">({ack.pending_directives.length})</span></h3>
            {ack.pending_directives.length === 0 ? (
              <p className="mt-1 text-sm text-ink2">{t.directivesNone}</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-1.5">{ack.pending_directives.map((d) => <li key={d}><Pill tone="warning">{d}</Pill></li>)}</ul>
            )}
          </section>
          <section>
            <h3 className="text-sm font-medium">{t.warnings} <span className="tabular-nums text-ink2">({ack.warnings.length})</span></h3>
            {ack.warnings.length === 0 ? (
              <p className="mt-1 text-sm text-ink2">{t.warningsNone}</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {ack.warnings.map((w) => (
                  <li key={w} className="text-sm"><code className="font-mono text-xs">{w}</code> <span className="text-ink2">{t.warningText[w] ?? ""}</span></li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </Card>

      {/* ---- approval: a person's explicit decision; the engine records it and recomputes the status */}
      <Card title={t.approvalTitle}>
        {state.status === "READY_TO_SEND" ? (
          <Notice tone="success">{t.approvalReady}</Notice>
        ) : reviewable ? (
          <ApprovalForm key={review.context} review={review} workspace={workspace} viewer={viewer} seen={seen} onDecided={onDecided} onReload={onReload} />
        ) : (
          <>
            {blocking.length > 0 && <p className="text-sm text-warning">{t.notReviewable} {blocking.join(", ")}</p>}
            {blocking.length === 0 && <p className="text-sm text-ink2">{m.approve.already}</p>}
          </>
        )}
        {state.status !== "READY_TO_SEND" && (
          <details className="mt-5 rounded-xl border border-line p-4">
            <summary className="cursor-pointer text-sm font-medium">{m.approve.cliTitle}</summary>
            <p className="mt-2 text-sm text-ink2">{t.approvalNone}</p>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-relaxed">
              {t.approvalSteps.map((step, i) => (
                <li key={i}>
                  {step}
                  {i === 2 && doc.sha256 && <code className="ml-2 rounded bg-surface2 px-1.5 py-0.5 font-mono text-sm">{confirmationPrefix(doc.sha256)}</code>}
                </li>
              ))}
            </ol>
            <p className="mt-4 text-xs font-medium uppercase tracking-wide text-ink2">{t.command}</p>
            <div className="mt-1.5 flex flex-wrap items-start gap-2">
              <code className="min-w-0 flex-1 select-all break-all rounded-lg border border-line bg-bg p-3 font-mono text-xs">{command}</code>
              <Button onClick={() => void copy()}>{copied ? m.preview.copied : t.copyCommand}</Button>
            </div>
          </details>
        )}
      </Card>

      {/* ---- hashes and limits */}
      <Card title={t.fingerprints}>
        <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
          {([[t.cvId, s.tailored_cv_id], [t.plan, s.reviewed.plan_sha256], [t.assembly, s.reviewed.assembly_sha256], [t.tex, s.reviewed.tex_sha256], [t.pdf, doc.sha256]] as [string, string | null][]).map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-ink2">{label}</dt>
              <dd><code className="break-all font-mono text-xs">{value ?? "—"}</code></dd>
            </div>
          ))}
        </dl>
      </Card>
      <details className="rounded-2xl border border-line bg-surface p-5">
        <summary className="cursor-pointer font-display text-lg font-semibold">{t.limits}</summary>
        <p className="mt-2 text-xs text-ink2">{t.limitsNote}</p>
        <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed">{s.limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </details>
    </div>
  );
}

const STALE = ["REVIEW_CONTEXT_CHANGED", "PDF_CHANGED_SINCE_VIEW", "PACKAGE_NOT_REVIEWABLE", "FINAL_DOCUMENT_MISSING"];

type Decision = "" | "APPROVED" | "REJECTED";

/** Nothing here is pre-checked, pre-filled or automatic. The adapter re-reads the disk and refuses stale contexts. */
function ApprovalForm({ review, workspace, viewer, seen, onDecided, onReload }: { review: PackageReview; workspace: string; viewer: ViewerInfo | null; seen: number[]; onDecided: (o: ApprovalDone) => void; onReload: () => void }) {
  const { m } = useApp();
  const t = m.approve;
  const sha = review.summary.document.sha256 ?? "";
  const [examined, setExamined] = useState(false);
  const [warningsRead, setWarningsRead] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [prefix, setPrefix] = useState("");
  const [decision, setDecision] = useState<Decision>("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);

  const shown = !!viewer && viewer.browserSha === viewer.engineSha && viewer.engineSha === sha;
  const pages = viewer?.pages ?? review.summary.document.pages ?? 0;
  const allSeen = shown && pages > 0 && seen.length >= pages;
  const prefixOk = prefix.trim().toLowerCase() === confirmationPrefix(sha);
  const missing: string[] = [];
  if (!shown) missing.push(t.needs.doc);
  else if (!allSeen) missing.push(t.needs.pages);
  if (!examined) missing.push(t.needs.examined);
  if (!warningsRead) missing.push(t.needs.warnings);
  if (!reviewer.trim()) missing.push(t.needs.reviewer);
  if (!prefixOk) missing.push(t.needs.prefix);
  if (!decision) missing.push(t.needs.decision);
  const ready = missing.length === 0;

  async function submit() {
    if (!viewer || !decision) return;
    setConfirming(false);
    setBusy(true);
    setFailure(null);
    const res = await adapter<ApprovalDone>(workspace, "package_approve", {
      name: review.summary.package, decision, reviewer: reviewer.trim(), note: note.trim() || undefined,
      context: review.context, viewed_sha256: viewer.browserSha, typed_prefix: prefix.trim(),
      confirm_examined: examined, confirm_final: true,
    });
    setBusy(false);
    if (!res.ok) return setFailure(res);
    onDecided(res);
  }

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-ink2">{t.intro}</p>
      <section aria-labelledby="ap-check">
        <h3 id="ap-check" className="text-sm font-medium">{t.checklist}</h3>
        <ul className="mt-2 space-y-1 text-sm">
          <li className={shown ? "text-success" : "text-ink2"}>{shown ? "✔ " : "○ "}{shown ? t.docShown : t.docNotShown}</li>
          <li className={allSeen ? "text-success" : "text-ink2"}>{allSeen ? "✔ " : "○ "}{t.pagesSeen.replace("{n}", String(Math.min(seen.length, pages))).replace("{total}", String(pages))}</li>
        </ul>
      </section>

      <div className="space-y-2">
        <label className="flex items-start gap-2.5 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-[var(--color-accent)]" checked={examined} disabled={!allSeen} onChange={(e) => setExamined(e.target.checked)} />
          <span>{t.examined}{!allSeen && <span className="block text-xs text-ink2">{t.examinedLocked}</span>}</span>
        </label>
        <label className="flex items-start gap-2.5 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-[var(--color-accent)]" checked={warningsRead} onChange={(e) => setWarningsRead(e.target.checked)} />
          <span>{t.readWarnings}</span>
        </label>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label htmlFor="ap-reviewer" className="block text-sm font-medium">{t.reviewer}</label>
          <input id="ap-reviewer" className={inputCls} value={reviewer} maxLength={120} autoComplete="off" onChange={(e) => setReviewer(e.target.value.replace(/[\r\n]/g, " "))} />
          <p className="mt-1 text-xs text-ink2">{t.reviewerHint}</p>
        </div>
        <div>
          <label htmlFor="ap-prefix" className="block text-sm font-medium">{t.prefix}</label>
          <input id="ap-prefix" className={inputCls + " font-mono"} value={prefix} maxLength={64} autoComplete="off" spellCheck={false} aria-describedby="ap-prefix-hint" onChange={(e) => setPrefix(e.target.value)} />
          <p id="ap-prefix-hint" className={"mt-1 text-xs " + (prefix ? (prefixOk ? "text-success" : "text-danger") : "text-ink2")}>{prefix ? (prefixOk ? "✔ " + t.prefixOk : t.prefixBad) : t.prefixHint}</p>
        </div>
      </div>

      <fieldset>
        <legend className="text-sm font-medium">{t.decision}</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {([["APPROVED", t.approve], ["REJECTED", t.reject]] as [Decision, string][]).map(([value, label]) => (
            <label key={value} className={"cursor-pointer rounded-lg border px-3.5 py-2 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent " + (decision === value ? "border-accent bg-surface2 font-medium" : "border-line hover:bg-surface2")}>
              <input type="radio" name="ap-decision" value={value} checked={decision === value} onChange={() => setDecision(value)} className="sr-only" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor="ap-note" className="block text-sm font-medium">{t.note}</label>
        <textarea id="ap-note" rows={2} maxLength={400} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>

      {failure && (
        <div role="alert" className="rounded-xl border border-danger/40 bg-dangerbg p-4 text-sm">
          <p className="font-medium">{t.errors[failure.code] ?? failure.message}</p>
          <p className="mt-1 font-mono text-xs text-ink2">{failure.code}</p>
          {failure.details.length > 0 && <ul className="mt-1 font-mono text-xs text-ink2">{failure.details.slice(0, 4).map((d, i) => <li key={i}>{d.code}</li>)}</ul>}
          {STALE.includes(failure.code) && <Button className="mt-3" onClick={onReload}>{t.reopen}</Button>}
        </div>
      )}

      {!ready && <p className="text-xs text-ink2">{t.missing} {missing.join(" · ")}</p>}
      <div className="flex justify-end">
        <Button variant="primary" disabled={!ready || busy} onClick={() => setConfirming(true)}>{busy ? t.submitting : t.submit}</Button>
      </div>
      {confirming && decision && (
        <ConfirmDialog
          title={t.confirmTitle}
          body={(decision === "APPROVED" ? t.confirmApprove : t.confirmReject).replace("{hash}", confirmationPrefix(sha)).replace("{reviewer}", reviewer.trim())}
          confirmLabel={decision === "APPROVED" ? t.confirmApproveBtn : t.confirmRejectBtn}
          cancelLabel={t.cancel}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void submit()}
        />
      )}
    </div>
  );
}
