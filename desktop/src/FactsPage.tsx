import { useEffect, useMemo, useState } from "react";
import { saveFact } from "./bridge";
import { pickText, useApp } from "./ctx";
import { emptyFactForm, factFormChanged, factRequest, factToForm, needsConfirmation, sectionGroup, slugId, today } from "./forms";
import type { FactForm } from "./forms";
import { Button, Card, FailureNotice, Field, Notice, Pill, ProblemList, StatusPill, inputCls } from "./ui";
import type { AdapterFailure, FactRec, FactStatus, Problem, SectionRec } from "./types";

type Group = "experience" | "education" | "skills";
const STATUSES: FactStatus[] = ["NOT_CONFIRMED", "DERIVED", "CONFIRMED", "WITHDRAWN"];

export default function FactsPage({ group }: { group: Group }) {
  const { m, state } = useApp();
  if (!state) return null;
  if (!state.facts.present) return <Notice tone="neutral" title={m.workspace.factsMissing} />;
  if (!state.facts.valid) {
    return (
      <Notice tone="danger" title={m.workspace.factsInvalid}>
        <ProblemList items={state.facts.errors} />
      </Notice>
    );
  }
  const intro = group === "education" ? m.facts.introEducation : group === "skills" ? m.facts.introSkills : m.facts.introExperiences;
  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{intro}</p>
      <FactList group={group} />
    </div>
  );
}

export function FactList({ group }: { group: Group }) {
  const { m, state, setDirty } = useApp();
  const facts = state!.facts;
  const [editing, setEditing] = useState<string | null>(null); // fact id, or "+new"
  const [flash, setFlash] = useState<Problem[] | null>(null);
  const sections = facts.sections ?? [];
  const mine = (facts.facts ?? []).filter((f) => sectionGroup(f.section) === group);
  const candidates = useMemo(() => {
    const inGroup = sections.filter((s) => sectionGroup(s.id) === group);
    return inGroup.length ? inGroup : sections;
  }, [sections, group]);
  const bySection = candidates.map((s) => ({ section: s, facts: mine.filter((f) => f.section === s.id) }));
  const orphans = mine.filter((f) => !candidates.some((s) => s.id === f.section));
  const grouped = orphans.length ? [...bySection, { section: { id: "", title: "—", line: 0 } as SectionRec, facts: orphans }] : bySection;

  useEffect(() => {
    if (editing === null) setDirty("facts", false);
  }, [editing, setDirty]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-ink2">
          {mine.length} {m.facts.countOf}
        </p>
        {editing === null && (
          <Button variant="primary" onClick={() => setEditing("+new")} disabled={!candidates.length}>
            + {m.facts.addFact}
          </Button>
        )}
      </div>

      {flash && (
        <Notice tone="success" title={m.common.saved}>
          <span className="text-ink2">{m.common.gitNote}</span>
          {flash.length > 0 && (
            <>
              <span className="mt-2 block font-medium">{m.common.downstream}</span>
              <ProblemList items={flash} />
            </>
          )}
        </Notice>
      )}

      {editing === "+new" && (
        <Card title={m.facts.newTitle}>
          <FactEditor
            key="new"
            mode="create"
            fact={null}
            sections={candidates}
            onDone={(problems) => {
              setEditing(null);
              setFlash(problems);
            }}
            onCancel={() => setEditing(null)}
          />
        </Card>
      )}

      {mine.length === 0 && editing !== "+new" && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center">
          <p className="font-medium">{m.facts.emptyTitle}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink2">{group === "education" ? m.facts.emptyEducation : m.facts.emptyBody}</p>
        </div>
      )}

      {grouped
        .filter((g) => g.facts.length)
        .map(({ section, facts: list }) => (
          <section key={section.id} aria-label={section.title} className="space-y-3">
            {group === "experience" && <h2 className="font-display text-lg font-semibold">{section.title}</h2>}
            {list.map((fact) =>
              editing === fact.id ? (
                <Card key={fact.id}>
                  <FactEditor
                    mode="update"
                    fact={fact}
                    sections={candidates}
                    onDone={(problems) => {
                      setEditing(null);
                      setFlash(problems);
                    }}
                    onCancel={() => setEditing(null)}
                  />
                </Card>
              ) : (
                <FactCard key={fact.id} fact={fact} onEdit={() => { setFlash(null); setEditing(fact.id); }} locked={editing !== null} />
              ),
            )}
          </section>
        ))}
    </div>
  );
}

function FactCard({ fact, onEdit, locked }: { fact: FactRec; onEdit: () => void; locked: boolean }) {
  const { m } = useApp();
  return (
    <article className="rise rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-base leading-relaxed">{fact.text}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusPill status={fact.status} />
            {fact.confirmed_on && <Pill>{m.facts.confirmedBadge} {fact.confirmed_on}</Pill>}
            {fact.technologies.map((x) => <Pill key={x}>{x}</Pill>)}
            {fact.supersedes && <Pill tone="warning">{m.facts.supersedesBadge} {fact.supersedes}</Pill>}
          </div>
          {(fact.note || fact.source) && (
            <p className="mt-3 text-sm text-ink2">
              {fact.source && <span>{m.facts.source}: {fact.source}. </span>}
              {fact.note && <span>{fact.note}</span>}
            </p>
          )}
          <code className="mt-3 block font-mono text-xs text-ink2">{fact.id}</code>
        </div>
        <Button onClick={onEdit} disabled={locked} aria-label={m.common.edit + " " + fact.id}>{m.common.edit}</Button>
      </div>
    </article>
  );
}

function FactEditor({ mode, fact, sections, onDone, onCancel }: { mode: "create" | "update"; fact: FactRec | null; sections: SectionRec[]; onDone: (problems: Problem[]) => void; onCancel: () => void }) {
  const { m, state, workspace, reload, setDirty } = useApp();
  const original = useMemo(() => (fact ? factToForm(fact) : emptyFactForm(sections[0]?.id ?? "")), [fact, sections]);
  const [form, setForm] = useState<FactForm>(original);
  const [decided, setDecided] = useState(false);
  const [date, setDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [leaving, setLeaving] = useState(false);
  const dirty = mode === "create" ? form.id.trim() !== "" || form.text.trim() !== "" : factFormChanged(original, form);
  const confirm = needsConfirmation(mode === "create" ? null : original, form);
  const blocked = confirm && (!decided || !date.trim());
  const idOk = mode === "update" || form.id === "" || slugId(form.id) === form.id;
  const canSave = dirty && !blocked && form.text.trim() !== "" && form.id.trim() !== "" && idOk && !saving;
  const set = <K extends keyof FactForm>(key: K, value: FactForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => {
    setDirty("facts", dirty);
  }, [dirty, setDirty]);

  async function submit() {
    setSaving(true);
    setFailure(null);
    const res = await saveFact(workspace, factRequest(form, mode, state!.facts.source_sha256!, confirm ? { decided, date } : null));
    setSaving(false);
    if (!res.ok) return setFailure(res);
    setDirty("facts", false);
    await reload();
    onDone(res.downstream);
  }

  const p = "f-" + (fact?.id ?? "new") + "-";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSave) void submit();
      }}
      className="space-y-5"
    >
      {mode === "create" && (
        <div className="grid gap-4 md:grid-cols-2">
          <Field id={p + "id"} label={m.facts.id} hint={idOk ? m.facts.idHelp : slugId(form.id)}>
            <input id={p + "id"} className={inputCls + " font-mono"} value={form.id} onChange={(e) => set("id", e.target.value)} placeholder="skill.example" autoComplete="off" spellCheck={false} aria-invalid={!idOk} />
          </Field>
          <Field id={p + "section"} label={m.facts.section}>
            <select id={p + "section"} className={inputCls} value={form.section} onChange={(e) => set("section", e.target.value)}>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>{s.title}</option>
              ))}
            </select>
          </Field>
        </div>
      )}
      <Field id={p + "text"} label={m.facts.text}>
        <textarea id={p + "text"} rows={3} className={inputCls} value={form.text} onChange={(e) => set("text", e.target.value)} />
      </Field>
      <div className="grid gap-4 md:grid-cols-2">
        <Field id={p + "status"} label={m.facts.status} hint={m.facts.statusHelp[form.status]}>
          <select id={p + "status"} className={inputCls} value={form.status} onChange={(e) => set("status", e.target.value as FactStatus)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{m.facts.statusLabels[s]}</option>
            ))}
          </select>
        </Field>
        <Field id={p + "lang"} label={m.facts.lang + " (" + m.common.optional + ")"}>
          <input id={p + "lang"} className={inputCls} value={form.lang} maxLength={2} onChange={(e) => set("lang", e.target.value.toLowerCase())} placeholder="en" />
        </Field>
        <Field id={p + "tech"} label={m.facts.technologies}>
          <input id={p + "tech"} className={inputCls} value={form.technologies} onChange={(e) => set("technologies", e.target.value)} />
        </Field>
        <Field id={p + "cap"} label={m.facts.capabilities}>
          <input id={p + "cap"} className={inputCls} value={form.capabilities} onChange={(e) => set("capabilities", e.target.value)} />
        </Field>
        <Field id={p + "src"} label={m.facts.source}>
          <input id={p + "src"} className={inputCls} value={form.source} onChange={(e) => set("source", e.target.value)} />
        </Field>
        <Field id={p + "sup"} label={m.facts.supersedes + " (" + m.common.optional + ")"}>
          <input id={p + "sup"} className={inputCls + " font-mono"} value={form.supersedes} onChange={(e) => set("supersedes", e.target.value)} />
        </Field>
      </div>
      <Field id={p + "note"} label={m.facts.note}>
        <input id={p + "note"} className={inputCls} value={form.note} onChange={(e) => set("note", e.target.value)} />
      </Field>

      {confirm && (
        <fieldset className="rounded-xl border border-warning/50 bg-warningbg p-4">
          <legend className="px-1 text-sm font-semibold text-warning">{m.facts.confirmTitle}</legend>
          <p className="text-sm leading-relaxed text-ink">{m.facts.confirmBody}</p>
          <label className="mt-3 flex cursor-pointer items-center gap-3 text-sm font-medium">
            <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={decided} onChange={(e) => setDecided(e.target.checked)} />
            {m.facts.confirmCheck}
          </label>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="w-64">
              <Field id={p + "date"} label={m.facts.confirmDate}>
                <input id={p + "date"} className={inputCls + " font-mono"} value={date} onChange={(e) => setDate(e.target.value)} placeholder="2026-01-31" />
              </Field>
            </div>
            <Button onClick={() => setDate(today())}>{m.facts.confirmToday}</Button>
          </div>
          {blocked && <p className="mt-2 text-xs text-ink2">{m.facts.confirmNeeded}</p>}
        </fieldset>
      )}
      {mode === "create" && <p className="text-xs text-ink2">{m.facts.createdStatus}</p>}

      {failure && <FailureNotice failure={failure} />}

      {leaving && (
        <Notice tone="warning" title={m.common.leaveTitle}>
          {m.common.leaveBody}
          <div className="mt-3 flex gap-2">
            <Button variant="danger" onClick={onCancel}>{m.common.leave}</Button>
            <Button onClick={() => setLeaving(false)}>{m.common.keepEditing}</Button>
          </div>
        </Notice>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {dirty && <Pill tone="warning">{m.common.unsaved}</Pill>}
        <div className="ml-auto flex gap-2">
          <Button onClick={() => (dirty ? setLeaving(true) : onCancel())} disabled={saving}>{m.common.cancel}</Button>
          <Button variant="primary" onClick={() => void submit()} disabled={!canSave}>{saving ? m.common.saving : m.common.save}</Button>
        </div>
      </div>
    </form>
  );
}

export function skillTitle(map: Record<string, string> | undefined, lang: "fr" | "en") {
  return pickText(map, lang);
}
