import { useEffect, useMemo, useState } from "react";
import { adapter, pickFile } from "./bridge";
import { useApp } from "./ctx";
import { IDENTITY_FIELDS, countDraft, draftToRequest, emptyBlock, emptyDraft, emptyLine, identityChosen, newKey, proposalToDraft, validDate } from "./cvimport";
import type { BlockKind, CvApplied, CvProposal, CvSource, Draft, DraftBlock, DraftCategory, DraftLine, FieldChoice } from "./cvimport";
import { today } from "./forms";
import { base64ToBytes } from "./packages";
import type { AdapterFailure } from "./types";
import { Button, Card, FailureNotice, Field, Notice, inputCls } from "./ui";

type Step = "source" | "review" | "done";
const KINDS: BlockKind[] = ["experience", "project", "education", "other"];
const checkCls = "mt-0.5 size-4 shrink-0 cursor-pointer accent-[var(--accent)]";

function Steps({ step }: { step: Step }) {
  const { m } = useApp();
  const items: [Step, string][] = [["source", m.cvImport.stepSource], ["review", m.cvImport.stepReview], ["done", m.cvImport.stepDone]];
  return (
    <ol className="flex flex-wrap gap-2 text-sm">
      {items.map(([id, label], index) => (
        <li key={id} aria-current={step === id ? "step" : undefined}
          className={"flex items-center gap-2 rounded-full border px-3 py-1 " + (step === id ? "border-accent bg-surface2 font-medium text-ink" : "border-line text-ink2")}>
          <span className="tabular-nums">{index + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function Check({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className={checkCls} />
      <span>{label}</span>
    </label>
  );
}

function ChoiceSelect({ id, value, onChange }: { id: string; value: FieldChoice; onChange: (v: FieldChoice) => void }) {
  const { m } = useApp();
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value as FieldChoice)} className={inputCls + " md:w-56"}>
      <option value="skip">{m.cvImport.choiceSkip}</option>
      <option value="private">{m.cvImport.choicePrivate}</option>
      <option value="public">{m.cvImport.choicePublic}</option>
    </select>
  );
}

function LineRow({ id, label, line, onChange, onRemove }: { id: string; label: string; line: DraftLine; onChange: (patch: Partial<DraftLine>) => void; onRemove: () => void }) {
  const { m } = useApp();
  return (
    <li className="rounded-lg border border-line bg-bg p-3">
      <label htmlFor={id} className="sr-only">{label}</label>
      <textarea id={id} rows={2} value={line.text} onChange={(e) => onChange({ text: e.target.value })} className={inputCls + " mt-0 resize-y"} />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <Check checked={line.confirmed} onChange={(confirmed) => onChange({ confirmed })} label={m.cvImport.confirmLine} />
        <Button variant="ghost" onClick={onRemove}>{m.cvImport.remove}</Button>
      </div>
    </li>
  );
}

function BlockEditor({ block, onChange, onRemove }: { block: DraftBlock; onChange: (next: DraftBlock) => void; onRemove: () => void }) {
  const { m } = useApp();
  const t = m.cvImport;
  const set = (patch: Partial<DraftBlock>) => onChange({ ...block, ...patch });
  const setLine = (key: string, patch: Partial<DraftLine>) => set({ bullets: block.bullets.map((l) => (l.key === key ? { ...l, ...patch } : l)) });
  const id = (name: string) => `${block.key}-${name}`;
  const hasLines = block.bullets.some((l) => l.text.trim());
  return (
    <section className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <div className="grid gap-4 md:grid-cols-2">
        <Field id={id("kind")} label={t.kind}>
          <select id={id("kind")} value={block.kind} onChange={(e) => set({ kind: e.target.value as BlockKind })} className={inputCls}>
            {KINDS.map((k) => <option key={k} value={k}>{t.kinds[k]}</option>)}
          </select>
        </Field>
        <Field id={id("title")} label={t.title}>
          <input id={id("title")} value={block.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} className={inputCls} />
        </Field>
        <Field id={id("subtitle")} label={t.subtitle}>
          <input id={id("subtitle")} value={block.subtitle} onChange={(e) => set({ subtitle: e.target.value })} maxLength={200} className={inputCls} />
        </Field>
        <Field id={id("period")} label={t.period}>
          <input id={id("period")} value={block.period} onChange={(e) => set({ period: e.target.value })} maxLength={200} className={inputCls} />
        </Field>
        <Field id={id("place")} label={t.place}>
          <input id={id("place")} value={block.place} onChange={(e) => set({ place: e.target.value })} maxLength={200} className={inputCls} />
        </Field>
      </div>
      {!block.title.trim() && hasLines && <p role="alert" className="mt-3 text-sm text-warning">{t.needTitle}</p>}
      <div className="mt-4">
        <Check checked={block.confirmed} onChange={(confirmed) => set({ confirmed })} label={t.confirmHeading} />
        {!block.confirmed && hasLines && <p className="mt-1 pl-6 text-xs text-ink2">{t.headingNotConfirmed}</p>}
      </div>
      <h4 className="mt-5 text-sm font-medium">{t.lines} <span className="tabular-nums text-ink2">({block.bullets.length})</span></h4>
      <ul className="mt-2 space-y-2">
        {block.bullets.map((line, index) => (
          <LineRow key={line.key} id={id("l" + line.key)} label={`${t.line} ${index + 1}`} line={line}
            onChange={(patch) => setLine(line.key, patch)} onRemove={() => set({ bullets: block.bullets.filter((l) => l.key !== line.key) })} />
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={() => set({ bullets: [...block.bullets, emptyLine()] })}>{t.addLine}</Button>
        <Button onClick={() => set({ confirmed: true, bullets: block.bullets.map((l) => ({ ...l, confirmed: true })) })}>{t.confirmAllBlock}</Button>
        <Button variant="ghost" className="ml-auto" onClick={onRemove}>{t.removeBlock}</Button>
      </div>
    </section>
  );
}

function CategoryEditor({ category, onChange, onRemove }: { category: DraftCategory; onChange: (next: DraftCategory) => void; onRemove: () => void }) {
  const { m } = useApp();
  const t = m.cvImport;
  const set = (patch: Partial<DraftCategory>) => onChange({ ...category, ...patch });
  const setItem = (key: string, patch: Partial<DraftLine>) => set({ items: category.items.map((i) => (i.key === key ? { ...i, ...patch } : i)) });
  return (
    <section className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <Field id={category.key + "-title"} label={t.category}>
        <input id={category.key + "-title"} value={category.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} className={inputCls + " md:w-80"} />
      </Field>
      <ul className="mt-3 grid gap-2 md:grid-cols-2">
        {category.items.map((item, index) => (
          <li key={item.key} className="flex items-center gap-2 rounded-lg border border-line bg-bg px-3 py-2">
            <input type="checkbox" checked={item.confirmed} onChange={(e) => setItem(item.key, { confirmed: e.target.checked })}
              aria-label={`${t.confirmLine} : ${item.text || t.skill}`} title={t.confirmLine} className={checkCls + " mt-0"} />
            <input value={item.text} onChange={(e) => setItem(item.key, { text: e.target.value })} maxLength={200}
              aria-label={`${t.skill} ${index + 1}`} className="min-w-0 flex-1 bg-transparent text-sm outline-none focus:underline" />
            <button type="button" onClick={() => set({ items: category.items.filter((i) => i.key !== item.key) })}
              aria-label={`${t.remove} : ${item.text || t.skill}`} title={t.remove} className="cursor-pointer rounded px-1.5 text-ink2 hover:bg-surface2 hover:text-ink">×</button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={() => set({ items: [...category.items, emptyLine()] })}>{t.addSkill}</Button>
        <Button onClick={() => set({ items: category.items.map((i) => ({ ...i, confirmed: true })) })}>{t.confirmAllCategory}</Button>
        <Button variant="ghost" className="ml-auto" onClick={onRemove}>{t.removeCategory}</Button>
      </div>
    </section>
  );
}

function Unclassified({ draft, onChange }: { draft: Draft; onChange: (next: Draft) => void }) {
  const { m } = useApp();
  const t = m.cvImport;
  const [targets, setTargets] = useState<Record<string, string>>({});
  if (draft.unclassified.length === 0) return null;
  const drop = (key: string) => onChange({ ...draft, unclassified: draft.unclassified.filter((u) => u.key !== key) });
  const add = (key: string, text: string) => {
    const target = targets[key] ?? draft.blocks[0]?.key;
    if (!target) return;
    onChange({
      ...draft,
      blocks: draft.blocks.map((b) => (b.key === target ? { ...b, bullets: [...b.bullets, emptyLine(text)] } : b)),
      unclassified: draft.unclassified.filter((u) => u.key !== key),
    });
  };
  return (
    <Card title={`${t.unclassifiedTitle} (${draft.unclassified.length})`}>
      <p className="text-sm text-ink2">{t.unclassifiedIntro}</p>
      <ul className="mt-3 space-y-2">
        {draft.unclassified.map((u) => (
          <li key={u.key} className="rounded-lg border border-line bg-bg p-3 text-sm">
            {u.section && <p className="text-xs uppercase tracking-wide text-ink2">{u.section}</p>}
            <p>{u.text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {draft.blocks.length > 0 && (
                <>
                  <label htmlFor={"u-" + u.key} className="text-xs text-ink2">{t.addTo}</label>
                  <select id={"u-" + u.key} value={targets[u.key] ?? draft.blocks[0].key} onChange={(e) => setTargets({ ...targets, [u.key]: e.target.value })} className={inputCls + " mt-0 w-auto max-w-xs"}>
                    {draft.blocks.map((b, i) => <option key={b.key} value={b.key}>{b.title.trim() || `${t.kinds[b.kind]} ${i + 1}`}</option>)}
                  </select>
                  <Button onClick={() => add(u.key, u.text)}>{t.add}</Button>
                </>
              )}
              <Button variant="ghost" onClick={() => drop(u.key)}>{t.ignore}</Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function ImportPage() {
  const { m, workspace, state, reload, navigate, setDirty } = useApp();
  const t = m.cvImport;
  const profile = state?.profile.valid ? state.profile.data ?? null : null;
  const languages = useMemo(() => (profile?.languages ?? []).filter((l) => l === "fr" || l === "en"), [profile]);
  const shownName = profile?.identity?.display_name;
  const currentName = shownName && !Array.isArray(shownName) ? shownName.value : "";

  const [step, setStep] = useState<Step>("source");
  const [language, setLanguage] = useState<string>(profile?.default_language ?? "fr");
  const [text, setText] = useState("");
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "read" | "parse" | "save">(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [date, setDate] = useState("");
  const [done, setDone] = useState<CvApplied | null>(null);

  useEffect(() => {
    setDirty("import", step === "review");
    return () => setDirty("import", false);
  }, [step, setDirty]);

  useEffect(() => {
    if (languages.length && !languages.includes(language as "fr" | "en")) setLanguage(languages[0]);
  }, [languages, language]);

  const counts = useMemo(() => countDraft(draft), [draft]);

  if (!state || !state.facts.present || !state.facts.valid || !profile) {
    return (
      <div className="space-y-3">
        <Notice tone="warning" title={t.needProfile} />
        <Button variant="primary" onClick={() => navigate("dashboard")}>{m.workspace.goDashboard}</Button>
      </div>
    );
  }

  async function chooseFile() {
    const picked = await pickFile(["pdf", "docx", "txt", "md"], "CV");
    if (!picked) return;
    setBusy("read");
    setFailure(null);
    setNote(null);
    const res = await adapter<CvSource>(workspace, "cv_source_read", { source: picked });
    if (!res.ok) {
      setFailure(res);
      setBusy(null);
      return;
    }
    setSourceName(res.name);
    if (res.kind === "pdf") {
      try {
        const { pdfToText } = await import("./pdfText");
        const found = await pdfToText(base64ToBytes(res.base64 ?? ""));
        setText(found);
        if (!found.trim()) setNote(t.noText);
      } catch {
        setText("");
        setNote(t.pdfFailed);
      }
    } else {
      setText(res.text ?? "");
    }
    setBusy(null);
  }

  async function analyse() {
    setBusy("parse");
    setFailure(null);
    setNote(null);
    const res = await adapter<CvProposal>(workspace, "cv_parse", { text });
    setBusy(null);
    if (!res.ok) {
      setFailure(res);
      return;
    }
    const next = proposalToDraft(res, currentName);
    if (next.blocks.length === 0 && next.skills.length === 0) setNote(t.nothingFound);
    if (languages.includes(res.language)) setLanguage(res.language);
    setDraft(next);
    setStep("review");
  }

  function manual() {
    setFailure(null);
    setNote(null);
    setDraft({ ...emptyDraft(), blocks: [emptyBlock()] });
    setStep("review");
  }

  async function save() {
    setBusy("save");
    setFailure(null);
    const res = await adapter<CvApplied>(workspace, "cv_apply", draftToRequest(draft, language, counts.confirmed ? date : ""));
    setBusy(null);
    if (!res.ok) {
      setFailure(res);
      return;
    }
    setDone(res);
    setStep("done");
    await reload();
  }

  const setBlock = (next: DraftBlock) => setDraft((d) => ({ ...d, blocks: d.blocks.map((b) => (b.key === next.key ? next : b)) }));
  const setCategory = (next: DraftCategory) => setDraft((d) => ({ ...d, skills: d.skills.map((c) => (c.key === next.key ? next : c)) }));
  const dateOk = counts.confirmed === 0 || validDate(date);
  const canSave = !busy && counts.untitled === 0 && dateOk && (counts.entries > 0 || identityChosen(draft) > 0);
  const parked = counts.entries - counts.placed;

  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{t.intro}</p>
      <Steps step={step} />

      {step === "source" && (
        <Card>
          <div className="grid gap-4 md:grid-cols-2">
            <Field id="imp-lang" label={t.language}>
              <select id="imp-lang" value={language} onChange={(e) => setLanguage(e.target.value)} className={inputCls}>
                {languages.map((l) => <option key={l} value={l}>{l === "fr" ? m.onboard.french : m.onboard.english}</option>)}
              </select>
            </Field>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={() => void chooseFile()} disabled={!!busy}>{busy === "read" ? t.reading : t.chooseFile}</Button>
            <p className="text-xs text-ink2">{t.fileHint}</p>
          </div>
          {sourceName && <p className="mt-3 text-sm text-ink2">{t.readFrom} <span className="font-mono">{sourceName}</span></p>}
          {note && <p role="status" className="mt-3 text-sm text-warning">{note}</p>}
          <div className="mt-4">
            <Field id="imp-text" label={t.textLabel} hint={t.textHint}>
              <textarea id="imp-text" rows={14} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} className={inputCls + " resize-y font-mono text-xs leading-relaxed"} />
            </Field>
          </div>
          {failure && <div className="mt-3"><FailureNotice failure={failure} /></div>}
          <div className="mt-5 flex flex-wrap justify-end gap-3">
            <Button onClick={manual} disabled={!!busy}>{t.manual}</Button>
            <Button variant="primary" onClick={() => void analyse()} disabled={!!busy || !text.trim()}>{busy === "parse" ? t.analysing : t.analyse}</Button>
          </div>
        </Card>
      )}

      {step === "review" && (
        <div className="space-y-6">
          <Notice tone="neutral">{t.reviewIntro}</Notice>
          {note && <Notice tone="warning" title={note} />}

          {(IDENTITY_FIELDS.some((f) => draft.identity[f].value) || draft.links.length > 0) && (
            <Card title={t.identityTitle}>
              <p className="text-sm text-ink2">{t.identityIntro}</p>
              <div className="mt-3 space-y-3">
                {IDENTITY_FIELDS.filter((f) => draft.identity[f].value || draft.identity[f].choice !== "skip").map((field) => (
                  <div key={field} className="flex flex-wrap items-end gap-3">
                    <div className="min-w-0 flex-1">
                      <Field id={"id-" + field} label={t.fields[field]}>
                        <input id={"id-" + field} value={draft.identity[field].value} maxLength={200} className={inputCls}
                          onChange={(e) => setDraft((d) => ({ ...d, identity: { ...d.identity, [field]: { ...d.identity[field], value: e.target.value } } }))} />
                      </Field>
                    </div>
                    <label htmlFor={"idc-" + field} className="sr-only">{t.fields[field]}</label>
                    <ChoiceSelect id={"idc-" + field} value={draft.identity[field].choice}
                      onChange={(choice) => setDraft((d) => ({ ...d, identity: { ...d.identity, [field]: { ...d.identity[field], choice } } }))} />
                  </div>
                ))}
                {draft.links.map((link) => {
                  const patch = (p: Partial<typeof link>) => setDraft((d) => ({ ...d, links: d.links.map((l) => (l.key === link.key ? { ...l, ...p } : l)) }));
                  return (
                    <div key={link.key} className="flex flex-wrap items-end gap-3">
                      <div className="w-40">
                        <Field id={"ll-" + link.key} label={t.linkLabel}>
                          <input id={"ll-" + link.key} value={link.label} maxLength={60} onChange={(e) => patch({ label: e.target.value })} className={inputCls} />
                        </Field>
                      </div>
                      <div className="min-w-0 flex-1">
                        <Field id={"lv-" + link.key} label={t.linkValue}>
                          <input id={"lv-" + link.key} value={link.value} maxLength={300} onChange={(e) => patch({ value: e.target.value })} className={inputCls} />
                        </Field>
                      </div>
                      <label htmlFor={"lc-" + link.key} className="sr-only">{link.label}</label>
                      <ChoiceSelect id={"lc-" + link.key} value={link.choice} onChange={(choice) => patch({ choice })} />
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          <section className="space-y-4" aria-labelledby="imp-blocks">
            <h2 id="imp-blocks" className="font-display text-lg font-semibold">{t.blocksTitle} <span className="tabular-nums text-ink2">({draft.blocks.length})</span></h2>
            {draft.blocks.map((block) => (
              <BlockEditor key={block.key} block={block} onChange={setBlock} onRemove={() => setDraft((d) => ({ ...d, blocks: d.blocks.filter((b) => b.key !== block.key) }))} />
            ))}
            <Button onClick={() => setDraft((d) => ({ ...d, blocks: [...d.blocks, emptyBlock()] }))}>{t.addBlock}</Button>
          </section>

          <section className="space-y-4" aria-labelledby="imp-skills">
            <h2 id="imp-skills" className="font-display text-lg font-semibold">{t.skillsTitle}</h2>
            {draft.skills.map((category) => (
              <CategoryEditor key={category.key} category={category} onChange={setCategory} onRemove={() => setDraft((d) => ({ ...d, skills: d.skills.filter((c) => c.key !== category.key) }))} />
            ))}
            <Button onClick={() => setDraft((d) => ({ ...d, skills: [...d.skills, { key: newKey(), title: "", technical: true, items: [emptyLine()] }] }))}>{t.addCategory}</Button>
          </section>

          <Unclassified draft={draft} onChange={setDraft} />

          <Card title={t.dateTitle}>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-48">
                <Field id="imp-date" label={t.dateTitle}>
                  <input id="imp-date" value={date} onChange={(e) => setDate(e.target.value)} placeholder="2026-01-31" inputMode="numeric" autoComplete="off" className={inputCls + " font-mono"} />
                </Field>
              </div>
              <Button onClick={() => setDate(today())}>{t.today}</Button>
            </div>
            <p className="mt-2 text-xs text-ink2">{t.dateHint}</p>
            {!dateOk && <p role="alert" className="mt-2 text-sm text-warning">{t.dateInvalid}</p>}
          </Card>

          {failure && <FailureNotice failure={failure} />}

          <div className="sticky bottom-0 -mx-2 rounded-xl border border-line bg-surface px-4 py-3 shadow-sm" aria-live="polite">
            <p className="text-sm font-medium">{t.summary(counts.entries, counts.confirmed, counts.placed)}</p>
            {parked > 0 && <p className="text-xs text-ink2">{t.parkedNote(parked)}</p>}
            {counts.untitled > 0 && <p className="text-xs text-warning">{t.untitled(counts.untitled)}</p>}
            <div className="mt-3 flex flex-wrap justify-end gap-3">
              <Button onClick={() => setStep("source")} disabled={!!busy}>{t.back}</Button>
              <Button variant="primary" onClick={() => void save()} disabled={!canSave}>{busy === "save" ? t.saving : t.save}</Button>
            </div>
          </div>
        </div>
      )}

      {step === "done" && done && (
        <div className="space-y-4">
          <Notice tone="success" title={t.doneTitle}>
            <p>{t.doneBody(done.facts_added, done.confirmed, done.parked)}</p>
            {done.identity_updated && <p>{t.doneIdentity}</p>}
          </Notice>
          {done.parked > 0 && <p className="text-xs text-ink2">{t.limits}</p>}
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => navigate("experiences")}>{t.seeExperiences}</Button>
            <Button onClick={() => navigate("offers")}>{t.addOffer}</Button>
            <Button variant="ghost" onClick={() => { setText(""); setSourceName(null); setDraft(emptyDraft()); setDone(null); setDate(""); setStep("source"); }}>{t.another}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
