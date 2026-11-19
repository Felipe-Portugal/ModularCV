import { useCallback, useEffect, useState } from "react";
import { adapter, isTauri, profileCreate, profilesList } from "./bridge";
import { useApp } from "./ctx";
import type { AdapterFailure, ManagedProfile } from "./types";
import { Button, FailureNotice, Field, Notice, Pill, inputCls } from "./ui";

type CvLang = "fr" | "en";

function samePath(a: string, b: string): boolean {
  const norm = (p: string) => p.replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
  return !!a && !!b && norm(a) === norm(b);
}

function LanguageField({ id, value, onChange }: { id: string; value: CvLang; onChange: (v: CvLang) => void }) {
  const { m } = useApp();
  return (
    <Field id={id} label={m.onboard.cvLanguage}>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as CvLang)} className={inputCls}>
        <option value="fr">{m.onboard.french}</option>
        <option value="en">{m.onboard.english}</option>
      </select>
    </Field>
  );
}

/**
 * The profiles the application keeps for the user, and the form that creates one. Creating a profile makes an empty
 * folder (Rust side), then asks the engine adapter to write a minimal valid fact base and profile into it.
 */
export function ProfilesCard({ onOpen }: { onOpen: (path: string, thenImport: boolean) => void }) {
  const { m, lang, workspace } = useApp();
  const t = m.onboard;
  const desktop = isTauri();
  const [base, setBase] = useState("");
  const [profiles, setProfiles] = useState<ManagedProfile[]>([]);
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [language, setLanguage] = useState<CvLang>(lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);

  const refresh = useCallback(async () => {
    if (!desktop) return;
    try {
      const listed = await profilesList();
      setBase(listed.base);
      setProfiles(listed.profiles);
    } catch (e) {
      setError(t.errors[String(e)] ?? String(e));
    }
  }, [desktop, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFailure(null);
    try {
      const made = await profileCreate(name);
      const init = await adapter<{ ok: true }>(made.path, "workspace_init", { display_name: displayName, language });
      await refresh();
      if (!init.ok) {
        setFailure(init);
        return;
      }
      setName("");
      setDisplayName("");
      onOpen(made.path, true);
    } catch (err) {
      setError(t.errors[String(err)] ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="profiles-title" className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
      <h2 id="profiles-title" className="font-display text-lg font-semibold">{t.profilesTitle}</h2>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink2">{t.profilesIntro}</p>

      {profiles.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-line px-4 py-3 text-sm text-ink2">{t.noProfiles}</p>
      ) : (
        <ul className="mt-4 divide-y divide-line rounded-lg border border-line">
          {profiles.map((p) => {
            const current = samePath(p.path, workspace);
            return (
              <li key={p.path} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-medium">{p.name}</span>
                  {current && <Pill tone="success">{t.opened}</Pill>}
                  {!p.ready && <Pill tone="warning">{t.notReady}</Pill>}
                </span>
                <Button onClick={() => onOpen(p.path, false)} disabled={current}>{t.open}</Button>
              </li>
            );
          })}
        </ul>
      )}

      <form onSubmit={(e) => void create(e)} className="mt-6 border-t border-line pt-5">
        <h3 className="font-medium">{t.newTitle}</h3>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <Field id="np-name" label={t.profileName} hint={t.profileNameHint}>
            <input id="np-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoComplete="off" spellCheck={false} className={inputCls} />
          </Field>
          <Field id="np-display" label={t.displayName}>
            <input id="np-display" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={120} autoComplete="name" className={inputCls} />
          </Field>
          <LanguageField id="np-lang" value={language} onChange={setLanguage} />
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
        {failure && <div className="mt-3"><FailureNotice failure={failure} /></div>}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          {base ? <p className="min-w-0 break-all text-xs text-ink2">{t.profilesFolder} : <span className="font-mono">{base}</span></p> : <span />}
          <Button type="submit" variant="primary" disabled={!desktop || busy || !name.trim() || !displayName.trim()}>
            {busy ? t.creating : t.create}
          </Button>
        </div>
      </form>
    </section>
  );
}

/** Shown when the open folder has neither a fact base nor a profile: the application can create both here. */
export function InitFolder() {
  const { m, lang, workspace, reload, navigate } = useApp();
  const t = m.onboard;
  const [displayName, setDisplayName] = useState("");
  const [language, setLanguage] = useState<CvLang>(lang);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);

  async function init(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailure(null);
    const res = await adapter<{ ok: true }>(workspace, "workspace_init", { display_name: displayName, language });
    setBusy(false);
    if (!res.ok) {
      setFailure(res);
      return;
    }
    await reload();
    navigate("import");
  }

  return (
    <form onSubmit={(e) => void init(e)} className="space-y-4">
      <Notice tone="neutral" title={t.emptyFolderTitle}>{t.emptyFolderBody}</Notice>
      <div className="grid gap-4 rounded-2xl border border-line bg-surface p-6 md:grid-cols-2">
        <Field id="if-display" label={t.displayName}>
          <input id="if-display" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={120} autoComplete="name" className={inputCls} />
        </Field>
        <LanguageField id="if-lang" value={language} onChange={setLanguage} />
        <div className="md:col-span-2">
          <Button type="submit" variant="primary" disabled={busy || !displayName.trim()}>{busy ? t.creating : t.initHere}</Button>
        </div>
      </div>
      {failure && <FailureNotice failure={failure} />}
    </form>
  );
}
