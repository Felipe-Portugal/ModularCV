import { useCallback, useEffect, useMemo, useState } from "react";
import { adapter, pickFile } from "./bridge";
import { useApp } from "./ctx";
import { EMPLOYMENT, emptyOfferForm, missingRequired, offerChanged, offerCreateRequest, offerToForm, offerUpdateRequest, suggestJobKey } from "./offers";
import type { OfferForm } from "./offers";
import { Button, Card, ConfirmDialog, FailureNotice, Field, Notice, Pill, ProblemList, inputCls } from "./ui";
import type { AdapterFailure, OfferImported, OfferRead, OfferSaved, OfferSummary, OffersList } from "./types";

type View =
  | { mode: "list" }
  | { mode: "new"; initial: OfferForm; note?: string }
  | { mode: "detail"; file: string };

export const SELECTED_OFFER_KEY = "mcv.adapt.offer";

export default function JobsPage() {
  const { m, workspace, navigate, setDirty } = useApp();
  const [view, setView] = useState<View>({ mode: "list" });
  const [list, setList] = useState<OffersList | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const res = await adapter<OffersList>(workspace, "offers_list");
    if (res.ok) {
      setList(res);
      setFailure(null);
    } else setFailure(res);
  }, [workspace]);

  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => () => setDirty("offer", false), [setDirty]);

  async function importFile() {
    const picked = await pickFile(["json", "txt", "md"]);
    if (!picked) return;
    setBusy(true);
    setNotice(null);
    const res = await adapter<OfferImported>(workspace, "offer_import", { source: picked });
    setBusy(false);
    if (!res.ok) return setFailure(res);
    setFailure(null);
    if (res.kind === "text") {
      setView({ mode: "new", initial: { ...emptyOfferForm(), description: res.text ?? "" }, note: m.jobs.textImported });
    } else {
      setNotice(m.jobs.imported);
      await refresh();
    }
  }

  function analyse(file: string) {
    try {
      localStorage.setItem(SELECTED_OFFER_KEY, file);
    } catch {
      /* session only */
    }
    navigate("adapt");
  }

  if (view.mode === "new") {
    return (
      <OfferEditor
        key="new"
        mode="create"
        initial={view.initial}
        note={view.note}
        onCancel={() => setView({ mode: "list" })}
        onSaved={async (file) => {
          setNotice(m.jobs.created);
          await refresh();
          setView({ mode: "detail", file });
        }}
      />
    );
  }
  if (view.mode === "detail") {
    return (
      <OfferDetail
        key={view.file}
        file={view.file}
        initialNotice={notice}
        onBack={async () => {
          setNotice(null);
          await refresh();
          setView({ mode: "list" });
        }}
        onAnalyse={analyse}
        onDeleted={async () => {
          setNotice(m.jobs.deleted);
          await refresh();
          setView({ mode: "list" });
        }}
        onChanged={refresh}
      />
    );
  }

  const offers = list?.offers ?? [];
  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{m.jobs.intro}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => setView({ mode: "new", initial: emptyOfferForm() })}>+ {m.jobs.add}</Button>
        <Button onClick={() => setView({ mode: "new", initial: emptyOfferForm(), note: m.jobs.pasteHelp })}>{m.jobs.paste}</Button>
        <Button onClick={() => void importFile()} disabled={busy} title={m.jobs.importHelp}>{m.jobs.import}</Button>
      </div>
      {notice && <Notice tone="success" title={notice} />}
      {failure && <FailureNotice failure={failure} />}
      {list && offers.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center">
          <p className="font-medium">{m.jobs.emptyTitle}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink2">{m.jobs.emptyBody}</p>
        </div>
      )}
      {!list && !failure && <p role="status" className="text-sm text-ink2">{m.workspace.loading}</p>}
      <ul className="grid gap-3 md:grid-cols-2">
        {offers.map((o) => (
          <OfferCard key={o.file} offer={o} onOpen={() => setView({ mode: "detail", file: o.file })} onAnalyse={() => analyse(o.file)} />
        ))}
      </ul>
    </div>
  );
}

function OfferCard({ offer, onOpen, onAnalyse }: { offer: OfferSummary; onOpen: () => void; onAnalyse: () => void }) {
  const { m } = useApp();
  return (
    <li className="rise flex flex-col rounded-2xl border border-line bg-surface p-5">
      <div className="min-w-0 flex-1">
        <h3 className="font-display truncate text-lg font-semibold">{offer.title ?? offer.file}</h3>
        <p className="mt-0.5 truncate text-sm text-ink2">{offer.company ?? "—"}{offer.location ? " · " + offer.location : ""}</p>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {!offer.valid && <Pill tone="danger">{m.jobs.invalid}</Pill>}
          {offer.language && <Pill>{m.jobs.languages[offer.language] ?? offer.language}</Pill>}
          {offer.employment_type && offer.employment_type !== "UNSPECIFIED" && <Pill>{m.jobs.employment[offer.employment_type] ?? offer.employment_type}</Pill>}
          {offer.description_chars != null && <Pill>{offer.description_chars} {m.jobs.chars}</Pill>}
          {!!offer.requirements && <Pill>{offer.requirements} {m.jobs.requirementsCount}</Pill>}
        </div>
        {!offer.valid && <ProblemList items={offer.errors} />}
      </div>
      <div className="mt-4 flex gap-2">
        <Button onClick={onOpen} aria-label={m.jobs.open + " " + offer.file}>{m.jobs.open}</Button>
        {offer.valid && <Button variant="primary" onClick={onAnalyse} aria-label={m.jobs.analyse + " " + offer.file}>{m.jobs.analyse}</Button>}
      </div>
    </li>
  );
}

function OfferDetail({ file, initialNotice, onBack, onAnalyse, onDeleted, onChanged }: { file: string; initialNotice?: string | null; onBack: () => void; onAnalyse: (f: string) => void; onDeleted: () => void; onChanged: () => void }) {
  const { m, workspace } = useApp();
  const [read, setRead] = useState<OfferRead | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(initialNotice ?? null);

  const load = useCallback(async () => {
    const res = await adapter<OfferRead>(workspace, "offer_read", { file });
    if (res.ok) {
      setRead(res);
      setFailure(null);
    } else setFailure(res);
  }, [workspace, file]);
  useEffect(() => {
    void load();
  }, [load]);

  if (failure) {
    return (
      <div className="space-y-3">
        <FailureNotice failure={failure} />
        <Button onClick={onBack}>{m.jobs.back}</Button>
      </div>
    );
  }
  if (!read) return <p role="status" className="text-sm text-ink2">{m.workspace.loading}</p>;
  const doc = read.document;

  if (editing && doc && read.valid) {
    return (
      <OfferEditor
        mode="update"
        file={file}
        sha={read.sha256}
        initial={offerToForm(doc)}
        onCancel={() => setEditing(false)}
        onSaved={async () => {
          setEditing(false);
          setNotice(m.jobs.updated);
          await load();
          await onChanged();
        }}
        onConflictReload={load}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={onBack}>← {m.jobs.back}</Button>
        <div className="ml-auto flex flex-wrap gap-2">
          {read.valid && <Button variant="primary" onClick={() => onAnalyse(file)}>{m.jobs.analyse}</Button>}
          {read.valid && <Button onClick={() => setEditing(true)}>{m.common.edit}</Button>}
          <Button variant="ghost" onClick={() => setDeleting(true)}>{m.jobs.delete}</Button>
        </div>
      </div>
      {notice && <Notice tone="success" title={notice} />}
      {!read.valid && (
        <Notice tone="danger" title={m.jobs.invalid}>
          <ProblemList items={read.errors} />
        </Notice>
      )}
      {doc && (
        <Card>
          <h2 className="font-display text-2xl font-semibold tracking-tight">{doc.title}</h2>
          <p className="mt-1 text-ink2">{doc.company}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {doc.language && <Pill>{m.jobs.languages[doc.language] ?? doc.language}</Pill>}
            {doc.employment_type && doc.employment_type !== "UNSPECIFIED" && <Pill>{m.jobs.employment[doc.employment_type] ?? doc.employment_type}</Pill>}
            {doc.location && <Pill>{doc.location}</Pill>}
            {doc.workplace_type && <Pill>{doc.workplace_type}</Pill>}
            {doc.posted_on && <Pill>{doc.posted_on}</Pill>}
          </div>
          {(doc.requirements ?? []).length > 0 && (
            <div className="mt-5">
              <h3 className="text-sm font-medium">{m.jobs.requirements}</h3>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {(doc.requirements ?? []).map((r) => (
                  <li key={r.id}><Pill tone={r.priority === "REQUIRED" ? "warning" : "neutral"}>{r.term} · {r.priority === "REQUIRED" ? m.jobs.required : m.jobs.preferred}</Pill></li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-5">
            <h3 className="text-sm font-medium">{m.jobs.description}</h3>
            <pre className="mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line bg-bg p-4 font-sans text-sm leading-relaxed">{doc.description}</pre>
          </div>
          {doc.source_url && (
            <p className="mt-4 text-xs text-ink2">
              {m.jobs.source}: <code className="break-all font-mono">{doc.source_url}</code> · {m.jobs.urlHelp}
            </p>
          )}
          <code className="mt-4 block font-mono text-xs text-ink2">{read.file}</code>
        </Card>
      )}
      {deleting && <DeleteDialog file={file} sha={read.sha256} onCancel={() => setDeleting(false)} onDeleted={onDeleted} />}
    </div>
  );
}

function DeleteDialog({ file, sha, onCancel, onDeleted }: { file: string; sha: string; onCancel: () => void; onDeleted: () => void }) {
  const { m, workspace } = useApp();
  const stem = file.replace(/\.json$/, "");
  const [typed, setTyped] = useState("");
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onCancel]);

  async function remove() {
    setBusy(true);
    const res = await adapter<{ ok: true }>(workspace, "offer_delete", { file, expected_sha256: sha, confirm: typed });
    setBusy(false);
    if (!res.ok) return setFailure(res);
    onDeleted();
  }

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4">
      <div role="alertdialog" aria-modal="true" aria-labelledby="del-title" aria-describedby="del-body" className="rise w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl">
        <h2 id="del-title" className="font-display text-lg font-semibold">{m.jobs.deleteTitle}</h2>
        <p id="del-body" className="mt-2 text-sm leading-relaxed text-ink2">{m.jobs.deleteBody} <code className="font-mono text-ink">{stem}</code></p>
        <label htmlFor="del-confirm" className="sr-only">{stem}</label>
        <input id="del-confirm" autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} className={inputCls + " font-mono"} autoComplete="off" spellCheck={false} />
        {failure && <div className="mt-3"><FailureNotice failure={failure} /></div>}
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel}>{m.common.cancel}</Button>
          <Button variant="danger" onClick={() => void remove()} disabled={typed !== stem || busy}>{m.jobs.deleteConfirm}</Button>
        </div>
      </div>
    </div>
  );
}

function OfferEditor({ mode, initial, file, sha, note, onCancel, onSaved, onConflictReload }: { mode: "create" | "update"; initial: OfferForm; file?: string; sha?: string; note?: string; onCancel: () => void; onSaved: (file: string) => void | Promise<void>; onConflictReload?: () => void }) {
  const { m, workspace, setDirty } = useApp();
  const [form, setForm] = useState<OfferForm>(initial);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [leaving, setLeaving] = useState(false);
  const dirty = offerChanged(initial, form);
  const missing = useMemo(() => missingRequired(form), [form]);
  const set = <K extends keyof OfferForm>(k: K, v: OfferForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const canSave = dirty && missing.length === 0 && !saving;

  useEffect(() => {
    setDirty("offer", dirty);
    return () => setDirty("offer", false);
  }, [dirty, setDirty]);

  async function save() {
    setSaving(true);
    setFailure(null);
    const request = mode === "create" ? offerCreateRequest(form) : offerUpdateRequest(file!, sha!, initial, form);
    const res = await adapter<OfferSaved>(workspace, "offer_save", request);
    setSaving(false);
    if (!res.ok) {
      setFailure(res);
      return;
    }
    setDirty("offer", false);
    await onSaved(res.file);
  }

  const id = (n: string) => "of-" + n;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSave) void save();
      }}
      className="space-y-6"
    >
      <h2 className="font-display text-xl font-semibold">{mode === "create" ? m.jobs.newTitle : m.jobs.editTitle}</h2>
      {note && <Notice tone="neutral" title={note} />}
      <Card>
        <div className="grid gap-4 md:grid-cols-2">
          <Field id={id("title")} label={m.jobs.fields.title + " *"}>
            <input id={id("title")} className={inputCls} value={form.title} onChange={(e) => set("title", e.target.value)} />
          </Field>
          <Field id={id("company")} label={m.jobs.fields.company + " *"}>
            <input id={id("company")} className={inputCls} value={form.company} onChange={(e) => set("company", e.target.value)} />
          </Field>
          <Field id={id("key")} label={m.jobs.fields.job_key + " *"} hint={m.jobs.keyHelp}>
            <div className="flex gap-2">
              <input id={id("key")} className={inputCls + " font-mono"} value={form.job_key} disabled={mode === "update"} onChange={(e) => set("job_key", e.target.value)} autoComplete="off" spellCheck={false} />
              {mode === "create" && (
                <Button className="mt-1.5 shrink-0" onClick={() => set("job_key", suggestJobKey(form.title, form.company))} disabled={!form.title.trim()}>{m.jobs.keySuggest}</Button>
              )}
            </div>
          </Field>
          <Field id={id("lang")} label={m.jobs.fields.language}>
            <select id={id("lang")} className={inputCls} value={form.language} onChange={(e) => set("language", e.target.value)}>
              {["auto", "fr", "en"].map((l) => <option key={l} value={l}>{m.jobs.languages[l]}</option>)}
            </select>
          </Field>
          <Field id={id("emp")} label={m.jobs.fields.employment_type}>
            <select id={id("emp")} className={inputCls} value={form.employment_type} onChange={(e) => set("employment_type", e.target.value)}>
              {EMPLOYMENT.map((k) => <option key={k} value={k}>{m.jobs.employment[k]}</option>)}
            </select>
          </Field>
          <Field id={id("loc")} label={m.jobs.fields.location}>
            <input id={id("loc")} className={inputCls} value={form.location} onChange={(e) => set("location", e.target.value)} />
          </Field>
        </div>
        <div className="mt-4">
          <Field id={id("desc")} label={m.jobs.fields.description + " *"}>
            <textarea id={id("desc")} rows={10} className={inputCls + " font-sans leading-relaxed"} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card title={m.jobs.requirements}>
        <p className="mb-3 text-xs text-ink2">{m.jobs.requirementsHelp}</p>
        <div className="space-y-3">
          {form.requirements.map((r, i) => (
            <div key={i} className="grid gap-3 md:grid-cols-[1fr_1fr_auto_auto] md:items-end">
              <Field id={id("rid" + i)} label={m.jobs.reqId}>
                <input id={id("rid" + i)} className={inputCls + " font-mono"} value={r.id} onChange={(e) => set("requirements", form.requirements.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))} />
              </Field>
              <Field id={id("rterm" + i)} label={m.jobs.reqTerm}>
                <input id={id("rterm" + i)} className={inputCls} value={r.term} onChange={(e) => set("requirements", form.requirements.map((x, j) => (j === i ? { ...x, term: e.target.value } : x)))} />
              </Field>
              <Field id={id("rprio" + i)} label={m.jobs.reqPriority}>
                <select id={id("rprio" + i)} className={inputCls} value={r.priority} onChange={(e) => set("requirements", form.requirements.map((x, j) => (j === i ? { ...x, priority: e.target.value as "REQUIRED" | "PREFERRED" } : x)))}>
                  <option value="REQUIRED">{m.jobs.required}</option>
                  <option value="PREFERRED">{m.jobs.preferred}</option>
                </select>
              </Field>
              <Button variant="ghost" onClick={() => set("requirements", form.requirements.filter((_, j) => j !== i))} aria-label={m.common.remove + " " + (r.term || r.id)}>{m.common.remove}</Button>
            </div>
          ))}
          <Button onClick={() => set("requirements", [...form.requirements, { id: "", term: "", priority: "REQUIRED" }])}>{m.jobs.addRequirement}</Button>
        </div>
      </Card>

      <Card title={m.jobs.source}>
        <div className="grid gap-4 md:grid-cols-2">
          <Field id={id("url")} label={m.jobs.fields.source_url} hint={m.jobs.urlHelp}>
            <input id={id("url")} className={inputCls + " font-mono"} value={form.source_url} onChange={(e) => set("source_url", e.target.value)} placeholder="https://" />
          </Field>
          <Field id={id("sys")} label={m.jobs.fields.source_system}>
            <input id={id("sys")} className={inputCls} value={form.source_system} onChange={(e) => set("source_system", e.target.value)} />
          </Field>
          <Field id={id("work")} label={m.jobs.fields.workplace_type}>
            <input id={id("work")} className={inputCls} value={form.workplace_type} onChange={(e) => set("workplace_type", e.target.value)} />
          </Field>
          <Field id={id("posted")} label={m.jobs.fields.posted_on}>
            <input id={id("posted")} className={inputCls + " font-mono"} value={form.posted_on} onChange={(e) => set("posted_on", e.target.value)} placeholder="2026-01-31" />
          </Field>
        </div>
      </Card>

      {failure && (
        <div className="space-y-2">
          <FailureNotice failure={failure} />
          {failure.code === "CONFLICT" && onConflictReload && <Button onClick={() => { onCancel(); onConflictReload(); }}>{m.workspace.reload}</Button>}
        </div>
      )}
      {leaving && (
        <ConfirmDialog title={m.common.leaveTitle} body={m.common.leaveBody} confirmLabel={m.common.leave} cancelLabel={m.common.keepEditing} onCancel={() => setLeaving(false)} onConfirm={onCancel} />
      )}
      <div className="sticky bottom-0 -mx-2 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface/95 px-4 py-3 backdrop-blur">
        {dirty ? <Pill tone="warning">{m.common.unsaved}</Pill> : <span className="text-sm text-ink2">{m.common.nothingToSave}</span>}
        {dirty && missing.length > 0 && <span className="text-xs text-ink2">{m.jobs.missing} {missing.map((k) => m.jobs.fields[k]).join(", ")}</span>}
        <div className="ml-auto flex gap-2">
          <Button onClick={() => (dirty ? setLeaving(true) : onCancel())} disabled={saving}>{m.common.cancel}</Button>
          <Button variant="primary" onClick={() => void save()} disabled={!canSave}>{saving ? m.common.saving : m.common.save}</Button>
        </div>
      </div>
    </form>
  );
}
