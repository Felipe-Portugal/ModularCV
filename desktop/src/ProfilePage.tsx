import { useEffect, useMemo, useState } from "react";
import { saveProfile } from "./bridge";
import { useApp } from "./ctx";
import { IDENTITY_FIELDS, profileChanged, profileChanges, profileToForm } from "./forms";
import type { ProfileForm } from "./forms";
import { Button, Card, Field, FailureNotice, Notice, Pill, ProblemList, VisibilityPill, VisibilityToggle, inputCls } from "./ui";
import type { AdapterFailure, IdentityEntry, Problem, ProfileDoc } from "./types";

export default function ProfilePage() {
  const { m, state } = useApp();
  const profile = state?.profile;
  if (!profile?.present) return <Notice tone="neutral" title={m.workspace.profileMissing} />;
  if (!profile.valid || !profile.data) {
    return (
      <Notice tone="danger" title={m.workspace.profileInvalid}>
        <ProblemList items={profile.errors} />
      </Notice>
    );
  }
  return <ProfileView doc={profile.data} sha={profile.source_sha256!} />;
}

function ProfileView({ doc, sha }: { doc: ProfileDoc; sha: string }) {
  const { m, workspace, reload, setDirty } = useApp();
  const original = useMemo(() => profileToForm(doc), [doc]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ProfileForm>(original);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [done, setDone] = useState<Problem[] | null>(null);
  const dirty = editing && profileChanged(original, form);

  useEffect(() => {
    setDirty("profile", dirty);
    return () => setDirty("profile", false);
  }, [dirty, setDirty]);

  function start() {
    setForm(original);
    setFailure(null);
    setDone(null);
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setFailure(null);
    const res = await saveProfile(workspace, { expected_sha256: sha, changes: profileChanges(original, form) });
    setSaving(false);
    if (!res.ok) return setFailure(res);
    setEditing(false);
    setDone(res.downstream);
    await reload();
  }

  const set = <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-base leading-relaxed text-ink2">{m.profile.intro}</p>
        {!editing && <Button variant="primary" onClick={start}>{m.common.edit}</Button>}
      </div>

      {done && (
        <Notice tone="success" title={m.common.saved}>
          <span className="text-ink2">{m.common.gitNote}</span>
          {done.length > 0 && (
            <>
              <span className="mt-2 block font-medium">{m.common.downstream}</span>
              <ProblemList items={done} />
            </>
          )}
        </Notice>
      )}

      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="space-y-6"
        >
          <Card title={m.profile.identity}>
            <p className="mb-4 text-xs text-ink2">{m.profile.emptyRemoves}</p>
            <div className="space-y-5">
              {IDENTITY_FIELDS.map((name) => (
                <div key={name} className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
                  <Field id={"id-" + name} label={m.profile.fields[name] + (name === "display_name" ? "" : " (" + m.common.optional + ")")}>
                    <input
                      id={"id-" + name}
                      className={inputCls}
                      value={form.identity[name].value}
                      required={name === "display_name"}
                      onChange={(e) => set("identity", { ...form.identity, [name]: { ...form.identity[name], value: e.target.value } })}
                    />
                  </Field>
                  <VisibilityToggle
                    name={"vis-" + name}
                    value={form.identity[name].visibility}
                    onChange={(v) => set("identity", { ...form.identity, [name]: { ...form.identity[name], visibility: v } })}
                  />
                </div>
              ))}
            </div>
          </Card>

          <Card title={m.profile.links}>
            <div className="space-y-4">
              {form.links.map((link, i) => (
                <div key={i} className="grid gap-3 md:grid-cols-[1fr_2fr_auto_auto] md:items-end">
                  <Field id={"ll-" + i} label={m.profile.linkLabel}>
                    <input id={"ll-" + i} className={inputCls} value={link.label} onChange={(e) => set("links", form.links.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                  </Field>
                  <Field id={"lv-" + i} label={m.profile.linkValue}>
                    <input id={"lv-" + i} className={inputCls + " font-mono"} value={link.value} required onChange={(e) => set("links", form.links.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                  </Field>
                  <VisibilityToggle name={"lvis-" + i} value={link.visibility} onChange={(v) => set("links", form.links.map((x, j) => (j === i ? { ...x, visibility: v } : x)))} />
                  <Button variant="ghost" onClick={() => set("links", form.links.filter((_, j) => j !== i))} aria-label={m.common.remove + " " + (link.label || link.value)}>
                    {m.common.remove}
                  </Button>
                </div>
              ))}
              <Button onClick={() => set("links", [...form.links, { label: "", value: "", visibility: "private" }])}>{m.profile.addLink}</Button>
            </div>
          </Card>

          <Card title={m.profile.languages}>
            <p className="text-sm text-ink2">{m.profile.languagesFixed}</p>
            <div className="mt-3 max-w-xs">
              <Field id="def-lang" label={m.profile.defaultLanguage}>
                <select id="def-lang" className={inputCls} value={form.defaultLanguage} onChange={(e) => set("defaultLanguage", e.target.value)}>
                  {doc.languages.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </Field>
            </div>
          </Card>

          <Card title={m.profile.policy}>
            <div className="space-y-5">
              <label className="flex cursor-pointer items-start gap-3 text-sm">
                <input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={form.requireDate} onChange={(e) => set("requireDate", e.target.checked)} />
                {m.profile.requireDate}
              </label>
              <Field id="never" label={m.profile.never}>
                <textarea id="never" rows={3} className={inputCls} value={form.never} onChange={(e) => set("never", e.target.value)} />
              </Field>
              <Field id="omit" label={m.profile.omit}>
                <textarea id="omit" rows={3} className={inputCls} value={form.omit} onChange={(e) => set("omit", e.target.value)} />
              </Field>
              <div className="grid gap-4 md:grid-cols-2">
                {doc.languages.map((l) => (
                  <Field key={l} id={"fw-" + l} label={m.profile.forbidden + " · " + l}>
                    <textarea id={"fw-" + l} rows={3} className={inputCls} value={form.forbidden[l] ?? ""} onChange={(e) => set("forbidden", { ...form.forbidden, [l]: e.target.value })} />
                  </Field>
                ))}
              </div>
            </div>
          </Card>

          {failure && <FailureNotice failure={failure} />}
          <div className="sticky bottom-0 -mx-2 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface/95 px-4 py-3 backdrop-blur">
            {dirty ? <Pill tone="warning">{m.common.unsaved}</Pill> : <span className="text-sm text-ink2">{m.common.nothingToSave}</span>}
            <div className="ml-auto flex gap-2">
              <Button
                onClick={() => {
                  setEditing(false);
                  setFailure(null);
                }}
                disabled={saving}
              >
                {dirty ? m.common.discard : m.common.cancel}
              </Button>
              <Button variant="primary" onClick={() => void save()} disabled={!dirty || saving}>
                {saving ? m.common.saving : m.common.save}
              </Button>
            </div>
          </div>
        </form>
      ) : (
        <>
          <Card title={m.profile.identity}>
            <dl className="grid gap-x-8 gap-y-4 md:grid-cols-2">
              {IDENTITY_FIELDS.map((name) => {
                const entry = doc.identity[name] as IdentityEntry | undefined;
                return (
                  <div key={name}>
                    <dt className="text-xs uppercase tracking-wide text-ink2">{m.profile.fields[name]}</dt>
                    <dd className="mt-1 flex flex-wrap items-center gap-2">
                      {entry ? <span className="text-base">{entry.value}</span> : <span className="text-ink2">{m.profile.notSet}</span>}
                      {entry && <VisibilityPill visibility={entry.visibility} />}
                    </dd>
                  </div>
                );
              })}
            </dl>
            {(doc.identity.links ?? []).length > 0 && (
              <div className="mt-6 border-t border-line pt-4">
                <h3 className="text-sm font-medium">{m.profile.links}</h3>
                <ul className="mt-2 space-y-2">
                  {(doc.identity.links ?? []).map((l, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium">{l.label ?? ""}</span>
                      <span className="font-mono text-ink2">{l.value}</span>
                      <VisibilityPill visibility={l.visibility} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card title={m.common.internal}>
            <dl className="grid gap-x-8 gap-y-4 md:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink2">{m.profile.languages}</dt>
                <dd className="mt-1 flex gap-2">
                  {doc.languages.map((l) => (
                    <Pill key={l} tone={l === doc.default_language ? "success" : "neutral"}>{l}{l === doc.default_language ? " ★" : ""}</Pill>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink2">{m.profile.requireDate}</dt>
                <dd className="mt-1">{doc.policy?.require_confirmation_date ? "✔" : "—"}</dd>
              </div>
              <TermList label={m.profile.never} items={doc.policy?.never_publish_terms} />
              <TermList label={m.profile.omit} items={doc.policy?.omit_by_default_terms} />
              {Object.entries(doc.policy?.forbidden_words ?? {}).map(([l, terms]) => (
                <TermList key={l} label={m.profile.forbidden + " · " + l} items={terms} />
              ))}
            </dl>
            {Object.keys(doc.families).length > 0 && (
              <div className="mt-6 border-t border-line pt-4">
                <h3 className="text-sm font-medium">{m.profile.families}</h3>
                <p className="mt-1 text-xs text-ink2">{m.profile.familiesNote}</p>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(doc.families).map(([id, fam]) => (
                    <li key={id}><Pill>{fam.label ?? id}</Pill></li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function TermList({ label, items }: { label: string; items?: string[] }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink2">{label}</dt>
      <dd className="mt-1 flex flex-wrap gap-1.5">
        {items?.length ? items.map((x) => <Pill key={x}>{x}</Pill>) : <span className="text-ink2">—</span>}
      </dd>
    </div>
  );
}
