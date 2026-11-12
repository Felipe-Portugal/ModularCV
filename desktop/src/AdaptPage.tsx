import { useCallback, useEffect, useMemo, useState } from "react";
import { Suspense, lazy } from "react";
import { adapter, revealInExplorer } from "./bridge";
import { useApp } from "./ctx";
import { SELECTED_OFFER_KEY } from "./JobsPage";
import { countByState, requiredGaps, rowLabel, sortRows } from "./offers";
import { SELECTED_PACKAGE_KEY, looksLikePackageName, suggestPackageName } from "./packages";
import { Button, Card, FailureNotice, Field, Notice, Pill, ProblemList, inputCls } from "./ui";
import type { AdaptOptions, AdapterFailure, AssembleResult, LatexStatus, MatrixResult, MatrixRow, MatrixState, OffersList, PackageCreated, PlanResult, ProvenanceInfo, RenderReport } from "./types";

const PdfViewer = lazy(() => import("./PdfViewer"));

const STATE_TONE: Record<MatrixState, "success" | "warning" | "neutral" | "danger"> = {
  DIRECT: "success",
  ADJACENT: "warning",
  ABSENT: "neutral",
  FORBIDDEN_TO_CLAIM: "danger",
};
const STATE_BAR: Record<MatrixState, string> = {
  DIRECT: "bg-success",
  ADJACENT: "bg-warning",
  ABSENT: "bg-ink2/40",
  FORBIDDEN_TO_CLAIM: "bg-danger",
};

function remember(): string {
  try {
    return localStorage.getItem(SELECTED_OFFER_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function AdaptPage() {
  const { m, workspace, setDirty } = useApp();
  const [step, setStep] = useState(0);
  const [offers, setOffers] = useState<OffersList | null>(null);
  const [offerFile, setOfferFile] = useState(remember);
  const [options, setOptions] = useState<AdaptOptions | null>(null);
  const [family, setFamily] = useState("");
  const [language, setLanguage] = useState("");
  const [busy, setBusy] = useState<null | "matrix" | "plan" | "save" | "render">(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [matrix, setMatrix] = useState<MatrixResult | null>(null);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [saved, setSaved] = useState<{ file: string; renamed: boolean } | null>(null);

  useEffect(() => () => setDirty("adapt", false), [setDirty]);

  useEffect(() => {
    void (async () => {
      const res = await adapter<OffersList>(workspace, "offers_list");
      if (res.ok) setOffers(res);
      else setFailure(res);
    })();
  }, [workspace]);

  const valid = useMemo(() => (offers?.offers ?? []).filter((o) => o.valid), [offers]);
  useEffect(() => {
    if (offers && offerFile && !valid.some((o) => o.file === offerFile)) setOfferFile("");
  }, [offers, valid, offerFile]);

  // options depend on the chosen offer; any change invalidates later steps
  useEffect(() => {
    setMatrix(null);
    setPlan(null);
    setSaved(null);
    setOptions(null);
    if (!offerFile) return;
    void (async () => {
      const res = await adapter<AdaptOptions>(workspace, "adapt_options", { file: offerFile });
      if (!res.ok) return setFailure(res);
      setFailure(null);
      setOptions(res);
      const first = res.families[0];
      setFamily((f) => (res.families.some((x) => x.id === f) ? f : (first?.id ?? "")));
      const detected = res.offer_language?.language;
      setLanguage((l) => (l && first?.languages.includes(l) ? l : detected && first?.languages.includes(detected) ? detected : (first?.languages[0] ?? "")));
    })();
  }, [workspace, offerFile]);

  const familyLanguages = options?.families.find((f) => f.id === family)?.languages ?? [];
  useEffect(() => {
    if (family && familyLanguages.length && !familyLanguages.includes(language)) setLanguage(familyLanguages[0]);
  }, [family, familyLanguages, language]);

  const request = { offer_file: offerFile, family, language };

  async function analyse() {
    setBusy("matrix");
    setFailure(null);
    setPlan(null);
    setSaved(null);
    const res = await adapter<MatrixResult>(workspace, "matrix", request);
    setBusy(null);
    if (!res.ok) return setFailure(res);
    setMatrix(res);
    setStep(1);
  }

  async function buildPlan(write: boolean, onExists?: "new_name") {
    setBusy(write ? "save" : "plan");
    setFailure(null);
    const res = await adapter<PlanResult>(workspace, "plan", { ...request, write, on_exists: onExists });
    setBusy(null);
    if (!res.ok) return setFailure(res);
    setPlan(res);
    if (write && res.written) {
      const expected = `${offerFile.replace(/\.json$/, "")}.${family}.${language}.json`;
      setSaved({ file: res.written.file, renamed: res.written.file !== expected });
      setStep(3);
    } else {
      setStep(2);
    }
  }

  const steps = m.adapt.steps;
  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{m.adapt.intro}</p>
      <ol className="flex flex-wrap gap-2" aria-label={m.adapt.title}>
        {steps.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              onClick={() => setStep(i)}
              disabled={(i === 1 && !matrix) || (i === 2 && !plan) || (i === 3 && !saved)}
              aria-current={step === i ? "step" : undefined}
              className={"flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 " + (step === i ? "border-accent bg-surface2 font-medium" : "border-line text-ink2 hover:bg-surface2")}
            >
              <span className={"grid size-5 place-items-center rounded-full text-xs " + (step === i ? "bg-accent text-accentink" : "bg-surface2")}>{i + 1}</span>
              {label}
            </button>
          </li>
        ))}
      </ol>

      {failure && <FailureNotice failure={failure} />}

      {step === 0 && (
        <Card title={m.adapt.chooseOffer}>
          {!offers && <p role="status" className="text-sm text-ink2">{m.workspace.loading}</p>}
          {offers && valid.length === 0 && <p className="text-sm text-ink2">{m.adapt.noOffers}</p>}
          <fieldset>
            <legend className="sr-only">{m.adapt.chooseOffer}</legend>
            <div className="grid gap-2 md:grid-cols-2">
              {valid.map((o) => (
                <label key={o.file} className={"cursor-pointer rounded-xl border p-3 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent " + (offerFile === o.file ? "border-accent bg-surface2" : "border-line hover:bg-surface2")}>
                  <input type="radio" className="sr-only" name="offer" value={o.file} checked={offerFile === o.file} onChange={() => setOfferFile(o.file)} />
                  <span className="block truncate font-medium">{o.title}</span>
                  <span className="block truncate text-sm text-ink2">{o.company}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {options && (
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <Field id="ad-family" label={m.adapt.family}>
                <select id="ad-family" className={inputCls} value={family} onChange={(e) => setFamily(e.target.value)}>
                  {options.families.map((f) => <option key={f.id} value={f.id}>{f.label ?? f.id}</option>)}
                </select>
              </Field>
              <Field id="ad-lang" label={m.adapt.language} hint={options.offer_language?.language ? `${m.adapt.languageDetected}: ${options.offer_language.language} (${m.adapt.languageMethod[options.offer_language.method ?? "declared"] ?? ""})` : undefined}>
                <select id="ad-lang" className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {familyLanguages.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </Field>
            </div>
          )}
          <div className="mt-5 flex justify-end">
            <Button variant="primary" onClick={() => void analyse()} disabled={!offerFile || !family || !language || busy !== null}>
              {busy === "matrix" ? m.adapt.analysing : m.adapt.analyse}
            </Button>
          </div>
        </Card>
      )}

      {step === 1 && matrix && (
        <>
          <MatrixView result={matrix} />
          <div className="flex justify-between">
            <Button onClick={() => setStep(0)}>{m.adapt.back}</Button>
            <Button variant="primary" onClick={() => void buildPlan(false)} disabled={busy !== null}>{busy === "plan" ? m.adapt.building : m.adapt.buildPlan}</Button>
          </div>
        </>
      )}

      {step === 2 && plan && (
        <>
          <PlanView plan={plan} />
          <div className="flex justify-between">
            <Button onClick={() => setStep(1)}>{m.adapt.back}</Button>
            <Button variant="primary" onClick={() => void buildPlan(true, "new_name")} disabled={busy !== null}>{busy === "save" ? m.adapt.saving : m.adapt.savePlan}</Button>
          </div>
        </>
      )}

      {step === 3 && saved && plan && (
        <GenerateStep offerFile={offerFile} family={family} language={language} planFile={saved.file} renamed={saved.renamed} provenance={plan.provenance} onBack={() => setStep(2)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- matrix

export function MatrixView({ result }: { result: MatrixResult }) {
  const { m } = useApp();
  const rows = useMemo(() => sortRows(result.matrix.requirements), [result]);
  const counts = countByState(rows);
  const gaps = requiredGaps(rows);
  const total = rows.length || 1;
  return (
    <div className="space-y-5">
      <Card title={m.adapt.matrixTitle}>
        <p className="text-sm text-ink2">{result.job.title} · {result.job.company}</p>
        <p className="mt-1 text-sm text-ink2">{m.adapt.matrixIntro}</p>
        <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-surface2" role="img" aria-label={(Object.keys(counts) as MatrixState[]).map((s) => `${m.adapt.states[s]} ${counts[s]}`).join(", ")}>
          {(Object.keys(counts) as MatrixState[]).map((s) => counts[s] > 0 && <span key={s} className={STATE_BAR[s]} style={{ width: `${(counts[s] / total) * 100}%` }} />)}
        </div>
        <ul className="mt-3 flex flex-wrap gap-2">
          {(Object.keys(counts) as MatrixState[]).map((s) => (
            <li key={s} title={m.adapt.stateHelp[s]}><Pill tone={STATE_TONE[s]}>{m.adapt.states[s]} · {counts[s]}</Pill></li>
          ))}
        </ul>
      </Card>

      {gaps.length > 0 ? (
        <Notice tone="warning" title={`${m.adapt.gapsTitle} (${gaps.length})`}>
          {m.adapt.gapsBody}
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {gaps.map((g) => <li key={g.id}><Pill tone={STATE_TONE[g.state]}>{rowLabel(g)} · {m.adapt.states[g.state]}</Pill></li>)}
          </ul>
        </Notice>
      ) : (
        <Notice tone="success" title={m.adapt.gapsNone} />
      )}

      <ul className="space-y-3">
        {rows.map((row) => <RequirementCard key={row.id} row={row} texts={result.texts} />)}
      </ul>
    </div>
  );
}

function RequirementCard({ row, texts }: { row: MatrixRow; texts: Record<string, string | null> }) {
  const { m } = useApp();
  return (
    <li className="rise rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{rowLabel(row)}</p>
          <p className="text-xs text-ink2">{row.kind ? m.adapt.kind[row.kind] ?? row.kind : ""}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={row.priority === "REQUIRED" ? "warning" : "neutral"}>{m.adapt.priority[row.priority]}</Pill>
          <span title={m.adapt.stateHelp[row.state]}><Pill tone={STATE_TONE[row.state]}>{m.adapt.states[row.state]}</Pill></span>
        </div>
      </div>
      <p className="mt-2 text-sm text-ink2">{m.adapt.stateHelp[row.state]}</p>
      {row.reasons.length > 0 && (
        <ul className="mt-2 text-sm">
          {row.reasons.map((r) => <li key={r} className="text-ink2">• {m.adapt.reasons[r] ?? r}</li>)}
        </ul>
      )}
      {row.forbidden_by.length > 0 && <p className="mt-2 text-sm text-danger">{m.adapt.forbiddenBy}: {row.forbidden_by.join(", ")}</p>}
      {row.evidence.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-xs uppercase tracking-wide text-ink2">{m.adapt.evidence}</p>
          <ul className="mt-1.5 space-y-1.5">
            {row.evidence.map((e) => (
              <li key={e.type + e.id} className="text-sm">
                <span className={e.relation === "ADJACENT" ? "text-warning" : ""}>{texts[`${e.type}:${e.id}`] ?? e.id}</span>
                {e.via && <span className="text-xs text-ink2"> · {m.adapt.via} {e.via}</span>}
                <code className="ml-2 font-mono text-xs text-ink2">{e.facts.join(", ")}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- plan

function PlanView({ plan }: { plan: PlanResult }) {
  const { m } = useApp();
  const p = plan.plan;
  const label = (type: string, id: string) => plan.texts[`${type}:${id}`] ?? id;
  const selected = [
    ...p.selected.blocks.map((b) => ({ type: "block", id: b.id, reason: b.reason })),
    ...p.selected.bullets.map((b) => ({ type: "bullet", id: b.id, reason: b.reason ?? "SELECTED" })),
    ...p.selected.skills.map((s) => ({ type: "skill", id: s.id, reason: s.reason ?? "SELECTED" })),
  ];
  return (
    <div className="space-y-5">
      <Notice tone="neutral" title={m.adapt.planTitle}>{m.adapt.planNotCv}</Notice>
      <ProvenanceCard info={plan.provenance} />
      {p.unsatisfied_required.length > 0 && (
        <Notice tone="warning" title={`${m.adapt.gapsTitle} (${p.unsatisfied_required.length})`}>
          {m.adapt.gapsBody}
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {p.unsatisfied_required.map((u) => <li key={u.id}><Pill tone={STATE_TONE[u.state]}>{u.id} · {m.adapt.states[u.state]}</Pill></li>)}
          </ul>
        </Notice>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={`${m.adapt.selected} (${selected.length})`}>
          {selected.length === 0 && <p className="text-sm text-ink2">{m.adapt.selectedNone}</p>}
          <ul className="space-y-2.5">
            {selected.map((s) => (
              <li key={s.type + s.id} className="text-sm">
                <p>{label(s.type, s.id)}</p>
                <p className="text-xs text-ink2"><code className="font-mono">{s.type}:{s.id}</code> · {m.adapt.selectionReasons[s.reason] ?? s.reason}</p>
              </li>
            ))}
          </ul>
        </Card>
        <Card title={`${m.adapt.omitted} (${p.omitted.length})`}>
          {p.omitted.length === 0 && <p className="text-sm text-ink2">{m.adapt.omittedNone}</p>}
          <ul className="space-y-2.5">
            {p.omitted.map((o) => (
              <li key={o.type + o.id} className="text-sm">
                <p className="text-ink2">{label(o.type, o.id)}</p>
                <p className="text-xs text-ink2"><code className="font-mono">{o.type}:{o.id}</code> · {m.adapt.omitReasons[o.reason] ?? o.reason}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      {p.warnings.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {p.warnings.map((w) => <li key={w.code}><Pill tone="warning">{w.code}</Pill></li>)}
        </ul>
      )}
      <p className="text-xs text-ink2">{p.limits[p.limits.length - 2]}</p>
    </div>
  );
}

function ProvenanceCard({ info }: { info: ProvenanceInfo }) {
  const { m } = useApp();
  if (info.status === "VERIFIED") {
    return <Notice tone="success" title={m.adapt.provenance}>{m.adapt.provenanceOk} <code className="font-mono">{info.commit?.slice(0, 12)}</code></Notice>;
  }
  return (
    <Notice tone="warning" title={m.adapt.provenance}>
      {m.adapt.provenanceNo}
      {info.reason && <span className="mt-1 block text-ink2">{m.adapt.provenanceReason[info.reason] ?? info.reason}{info.path ? ` : ${info.path}` : ""}</span>}
      {!info.reason && info.code && <span className="mt-1 block font-mono text-xs text-ink2">{info.code}</span>}
    </Notice>
  );
}

// ---------------------------------------------------------------- generation

function GenerateStep({ offerFile, family, language, planFile, renamed, provenance, onBack }: { offerFile: string; family: string; language: string; planFile: string; renamed: boolean; provenance: ProvenanceInfo; onBack: () => void }) {
  const { m, workspace } = useApp();
  const [name, setName] = useState("");
  const [paper, setPaper] = useState("a4paper");
  const [latex, setLatex] = useState<LatexStatus | null>(null);
  const [verify, setVerify] = useState<"pending" | "ok" | AdapterFailure>("pending");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [report, setReport] = useState<RenderReport | null>(null);
  const [lastPdf, setLastPdf] = useState(false);

  const check = useCallback(async () => {
    setVerify("pending");
    const res = await adapter<AssembleResult>(workspace, "assemble", { offer_file: offerFile, plan_file: planFile });
    setVerify(res.ok ? "ok" : res);
  }, [workspace, offerFile, planFile]);

  useEffect(() => {
    void check();
    void (async () => {
      const res = await adapter<LatexStatus>(workspace, "latex_status");
      if (res.ok) setLatex(res);
    })();
  }, [check, workspace]);

  async function generate(pdf: boolean, onExists?: "new_name") {
    setBusy(true);
    setFailure(null);
    setLastPdf(pdf);
    const res = await adapter<RenderReport>(workspace, "render", { offer_file: offerFile, plan_file: planFile, name: name || undefined, paper, compile: pdf, on_exists: onExists });
    setBusy(false);
    if (!res.ok) return setFailure(res);
    setReport(res);
  }

  const suggested = failure?.code === "OUTPUT_EXISTS" ? failure.details.find((d) => d.code === "SUGGESTED_NAME")?.message : undefined;
  const verified = verify === "ok";

  return (
    <div className="space-y-5">
      <Card title={m.adapt.generate}>
        <p className="text-sm text-ink2">{m.adapt.planSaved} <code className="font-mono text-ink">plans/{planFile}</code></p>
        {renamed && <p className="mt-1 text-xs text-ink2">{m.adapt.planNew}</p>}
        <div className="mt-3">
          {verify === "pending" && <p role="status" className="text-sm text-ink2">{m.adapt.previewHint}</p>}
          {verified && <Pill tone="success">{m.adapt.previewTitle} ✔</Pill>}
          {typeof verify === "object" && (
            <Notice tone="danger" title={m.adapt.stale}>
              <FailureNotice failure={verify} />
            </Notice>
          )}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field id="gen-name" label={m.adapt.outputName}>
            <input id="gen-name" className={inputCls + " font-mono"} value={name} onChange={(e) => setName(e.target.value)} placeholder="my-cv" autoComplete="off" spellCheck={false} />
          </Field>
          <Field id="gen-paper" label={m.adapt.paper}>
            <select id="gen-paper" className={inputCls} value={paper} onChange={(e) => setPaper(e.target.value)}>
              <option value="a4paper">A4</option>
              <option value="letterpaper">Letter</option>
            </select>
          </Field>
        </div>
        <p className="mt-3 text-xs text-ink2">{latex?.pdflatex === "FOUND" ? `${m.adapt.latexFound} (${latex.distribution ?? ""})` : latex ? m.adapt.latexAbsent : ""}</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button onClick={() => void generate(false)} disabled={busy || !verified}>{busy && !lastPdf ? m.adapt.generating : m.adapt.generate}</Button>
          <Button variant="primary" onClick={() => void generate(true)} disabled={busy || !verified}>{busy && lastPdf ? m.adapt.generating : m.adapt.generatePdf}</Button>
        </div>
      </Card>

      <ProvenanceCard info={provenance} />

      {failure && (
        <div className="space-y-2">
          <FailureNotice failure={failure} />
          {suggested && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-ink2">{m.adapt.suggested}:</span> <code className="font-mono">{suggested}</code>
              <Button onClick={() => void generate(lastPdf, "new_name")}>{m.adapt.useNewName}</Button>
            </div>
          )}
        </div>
      )}

      {report && <ReportCard report={report} />}
      <PackageCard offerFile={offerFile} family={family} language={language} planFile={planFile} texFile={report ? report.tex.file.replace(/^out\//, "") : null} verified={verified} latex={latex} />
      <div className="flex justify-between">
        <Button onClick={onBack}>{m.adapt.back}</Button>
        <OutputsFolder />
      </div>
    </div>
  );
}

function OutputsFolder() {
  const { m, workspace } = useApp();
  return <Button variant="ghost" onClick={() => void revealInExplorer(workspace, "out").catch(() => revealInExplorer(workspace))}>{m.adapt.reveal}</Button>;
}

function ReportCard({ report }: { report: RenderReport }) {
  const { m, workspace } = useApp();
  const pdf = report.pdf;
  const [showPreview, setShowPreview] = useState(false);
  const outputBase = pdf.file ? pdf.file.replace(/^out\//, "").replace(/\.pdf$/, "") : null;
  return (
    <Card title={m.adapt.generated}>
      <ul className="space-y-3">
        <li className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium">{m.adapt.texLabel}</p>
            <code className="font-mono text-xs text-ink2">{report.tex.file}</code>
          </div>
          <Button variant="ghost" onClick={() => void revealInExplorer(workspace, report.tex.file)}>{m.adapt.reveal}</Button>
        </li>
        <li className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium">{m.adapt.pdfLabel}</p>
            {pdf.status === "COMPILED" && <code className="font-mono text-xs text-ink2">{pdf.file} · {pdf.pages} {m.adapt.pages}</code>}
            {pdf.status === "UNAVAILABLE" && <p className="text-sm text-warning">{m.adapt.latexAbsent}</p>}
            {pdf.status === "FAILED" && <p className="text-sm text-danger">{m.adapt.pdfFailed} {pdf.message}</p>}
            {pdf.status === "NOT_REQUESTED" && <p className="text-xs text-ink2">—</p>}
          </div>
          {pdf.status === "COMPILED" && pdf.file && (
            <div className="flex gap-2">
              <Button aria-expanded={showPreview} onClick={() => setShowPreview((v) => !v)}>{showPreview ? m.history.hidePreview : m.history.preview}</Button>
              <Button variant="ghost" onClick={() => void revealInExplorer(workspace, pdf.file!)}>{m.adapt.reveal}</Button>
            </div>
          )}
        </li>
      </ul>
      {showPreview && outputBase && (
        <div className="mt-4">
          <Suspense fallback={<p role="status" className="text-sm text-ink2">{m.preview.loading}</p>}>
            <PdfViewer target={{ output: outputBase }} exact="output" />
          </Suspense>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-1.5">
        {report.layout.pages != null && <Pill tone={report.layout.page_verdict === "TARGET_EXCEEDED" ? "warning" : "success"}>{m.adapt.pageVerdict[report.layout.page_verdict] ?? report.layout.page_verdict}</Pill>}
        <Pill>NOT_REVIEWED</Pill>
        {report.warnings.map((w) => <Pill key={w} tone="warning">{w}</Pill>)}
      </div>
      <p className="mt-3 text-sm text-ink2">{m.adapt.notReady}</p>
      {report.pending_directives > 0 && <ProblemList items={[]} />}
    </Card>
  );
}

// ---------------------------------------------------------------- package (engine `package create --compile`)

function PackageCard({ offerFile, family, language, planFile, texFile, verified, latex }: { offerFile: string; family: string; language: string; planFile: string; texFile: string | null; verified: boolean; latex: LatexStatus | null }) {
  const { m, workspace, navigate } = useApp();
  const t = m.package;
  const [name, setName] = useState(() => suggestPackageName(offerFile.replace(/\.json$/, ""), family, language));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [created, setCreated] = useState<PackageCreated | null>(null);

  async function create() {
    if (!texFile) return;
    setBusy(true);
    setFailure(null);
    setCreated(null);
    const res = await adapter<PackageCreated>(workspace, "package_create", { name, offer_file: offerFile, plan_file: planFile, tex_file: texFile });
    setBusy(false);
    if (!res.ok) return setFailure(res);
    setCreated(res);
  }

  function review(pkg: string) {
    try {
      localStorage.setItem(SELECTED_PACKAGE_KEY, pkg);
    } catch {
      /* optional convenience */
    }
    navigate("review");
  }

  return (
    <Card title={t.title}>
      <p className="text-sm leading-relaxed text-ink2">{t.intro}</p>
      <p className="mt-2 text-xs text-ink2">{t.freshPdf}</p>
      <p className="mt-2 text-xs text-ink2">{t.needGit}</p>
      {!texFile && <p className="mt-3 text-sm text-warning">{t.needTex}</p>}
      {latex?.pdflatex === "ABSENT" && <p className="mt-3 text-sm text-warning">{m.adapt.latexAbsent}</p>}
      <div className="mt-4">
        <Field id="pkg-name" label={t.name} hint={t.nameHint}>
          <input id="pkg-name" className={inputCls + " font-mono"} value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" spellCheck={false} />
        </Field>
      </div>
      <div className="mt-4 flex justify-end">
        <Button variant="primary" onClick={() => void create()} disabled={busy || !verified || !texFile || !looksLikePackageName(name)}>{busy ? t.creating : t.create}</Button>
      </div>
      {busy && <div className="sweep relative mt-3 h-1.5 overflow-hidden rounded-full bg-surface2" />}
      {failure && <div className="mt-4"><FailureNotice failure={failure} /></div>}
      {created && (
        <div className="mt-4">
          <Notice tone="success" title={`${t.created} ${created.package.name}`}>
            {t.createdBody} <code className="font-mono">{created.package.state}</code>. {t.notApproval}
          </Notice>
          <div className="mt-3 flex justify-end">
            <Button variant="primary" onClick={() => review(created.package.name)}>{t.review}</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
