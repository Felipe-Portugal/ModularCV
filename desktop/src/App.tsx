import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isTauri, pickFolder, prepareDemoWorkspace, readWorkspace, validateWorkspace } from "./bridge";
import { AppCtx, useApp } from "./ctx";
import type { Ctx } from "./ctx";
import AdaptPage from "./AdaptPage";
import FactsPage from "./FactsPage";
import DiagnosticsCard from "./DiagnosticsCard";
import HistoryPage from "./HistoryPage";
import JobsPage from "./JobsPage";
import { dictionaries, resolveLang } from "./i18n";
import type { Dict } from "./i18n";
import ProfilePage from "./ProfilePage";
import ReviewPage from "./ReviewPage";
import SkillsPage from "./SkillsPage";
import { strings } from "./strings";
import type { Strings } from "./strings";
import type { AdapterFailure, DemoKind, LangPref, Page, ThemePref, ValidationResult, WorkspaceState } from "./types";
import { Button, ConfirmDialog, FailureNotice, inputCls } from "./ui";
import { isSuccess, shortHash, toneOf } from "./view";

function load<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function loadText(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: preference is session-only */
  }
}

const PAGES: { id: Page; ready: boolean }[] = [
  { id: "dashboard", ready: true },
  { id: "profile", ready: true },
  { id: "experiences", ready: true },
  { id: "education", ready: true },
  { id: "skills", ready: true },
  { id: "offers", ready: true },
  { id: "adapt", ready: true },
  { id: "history", ready: true },
  { id: "review", ready: true },
  { id: "settings", ready: true },
];

const ICONS: Record<Page, string> = {
  dashboard: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z",
  profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6",
  experiences: "M4 7h16v13H4zM9 7V4h6v3M4 13h16",
  education: "M2 9l10-5 10 5-10 5zM6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5",
  skills: "M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z",
  offers: "M5 3h14v18l-7-4-7 4z",
  adapt: "M4 20l4-1 11-11-3-3L5 16zM14 6l3 3",
  history: "M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 7v5l3 2",
  review: "M12 3l9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v8",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 1-2-1V5h-4v2l-2 1-2-1-2 4 2 1v2l-2 1 2 4 2-1 2 1v2h4v-2l2-1 2 1 2-4-2-1z",
};

function Icon({ page }: { page: Page }) {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d={ICONS[page]} />
    </svg>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [themePref, setThemePref] = useState<ThemePref>(() => load("mcv.theme", ["system", "light", "dark"] as const, "system"));
  const [langPref, setLangPref] = useState<LangPref>(() => load("mcv.lang", ["system", "fr", "en"] as const, "system"));
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  const [workspace, setWorkspaceRaw] = useState(() => loadText("mcv.workspace"));
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [loadError, setLoadError] = useState<AdapterFailure | null>(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const dirtyKeys = useRef(new Set<string>());
  const requestId = useRef(0);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const dark = themePref === "dark" || (themePref === "system" && systemDark);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  const lang = resolveLang(langPref, navigator.language || "en");
  const t = dictionaries[lang];
  const m = strings[lang];
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const load_ = useCallback(async (path: string) => {
    if (!path || !isTauri()) {
      setState(null);
      return;
    }
    const id = ++requestId.current;
    setLoading(true);
    const res = await readWorkspace(path);
    if (id !== requestId.current) return; // a newer request superseded this one
    setLoading(false);
    if (res.ok) {
      setState(res);
      setLoadError(null);
    } else {
      setState(null);
      setLoadError(res);
    }
  }, []);

  useEffect(() => {
    void load_(workspace);
  }, [workspace, load_]);

  const setDirty = useCallback((key: string, dirty: boolean) => {
    if (dirty) dirtyKeys.current.add(key);
    else dirtyKeys.current.delete(key);
  }, []);

  /** Run `action` now, or after the user accepts losing unsaved changes. */
  const guard = useCallback((action: () => void) => {
    if (dirtyKeys.current.size === 0) action();
    else setPending(() => action);
  }, []);

  const navigate = useCallback((p: Page) => guard(() => setPage(p)), [guard]);
  const changeWorkspace = useCallback(
    (path: string) =>
      guard(() => {
        dirtyKeys.current.clear();
        setWorkspaceRaw(path);
        save("mcv.workspace", path);
      }),
    [guard],
  );
  const reload = useCallback(() => load_(workspace), [load_, workspace]);

  const ctx: Ctx = useMemo(
    () => ({ t, m, lang, workspace, state, loading, loadError, reload, navigate, setDirty }),
    [t, m, lang, workspace, state, loading, loadError, reload, navigate, setDirty],
  );

  const current = PAGES.find((p) => p.id === page)!;
  const needsWorkspace = ["profile", "experiences", "education", "skills", "offers", "adapt", "history", "review"].includes(page);

  return (
    <AppCtx.Provider value={ctx}>
      <div className="flex h-full flex-col md:flex-row">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accentink">
          {t.skip}
        </a>
        <Sidebar t={t} page={page} onNavigate={navigate} />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-6 py-4 md:px-10">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-widest text-ink2">{t.appName}</p>
              <h1 className="font-display truncate text-2xl font-semibold tracking-tight">{t.nav[page]}</h1>
            </div>
            <div className="flex min-w-0 items-center gap-2">
              {workspace && (
                <span title={workspace} className="max-w-[16rem] truncate rounded-full border border-line bg-surface px-3 py-1 font-mono text-xs text-ink2">
                  {workspace.split(/[\\/]/).filter(Boolean).pop()}
                </span>
              )}
              <span className="shrink-0 rounded-full border border-line bg-surface2 px-3 py-1 text-xs text-ink2">{t.prototype}</span>
            </div>
          </header>
          <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto px-6 py-8 md:px-10">
            <div key={page} className="rise mx-auto max-w-4xl">
              {page === "dashboard" && <Dashboard t={t} m={m} workspace={workspace} onWorkspace={changeWorkspace} state={state} loading={loading} />}
              {page === "settings" && (
                <Settings
                  t={t}
                  themePref={themePref}
                  langPref={langPref}
                  onTheme={(v) => { setThemePref(v); save("mcv.theme", v); }}
                  onLang={(v) => { setLangPref(v); save("mcv.lang", v); }}
                />
              )}
              {needsWorkspace && <WorkspaceGate page={page} />}
              {!current.ready && <NotImplemented t={t} title={t.nav[page]} />}
            </div>
          </main>
        </div>
      </div>
      {pending && (
        <ConfirmDialog
          title={m.common.leaveTitle}
          body={m.common.leaveBody}
          confirmLabel={m.common.leave}
          cancelLabel={m.common.stay}
          onCancel={() => setPending(null)}
          onConfirm={() => {
            const action = pending;
            dirtyKeys.current.clear();
            setPending(null);
            action();
          }}
        />
      )}
    </AppCtx.Provider>
  );
}

function WorkspaceGate({ page }: { page: Page }) {
  const { m, state, loading, loadError, workspace, navigate, reload } = useApp();
  if (!workspace) {
    return (
      <div className="rounded-2xl border border-dashed border-line p-10 text-center">
        <p className="font-display text-lg font-semibold">{m.workspace.needTitle}</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink2">{m.workspace.needBody}</p>
        <Button variant="primary" className="mt-5" onClick={() => navigate("dashboard")}>{m.workspace.goDashboard}</Button>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="space-y-3">
        <FailureNotice failure={loadError} />
        <Button onClick={() => void reload()}>{m.workspace.reload}</Button>
      </div>
    );
  }
  if (!state) {
    return (
      <div role="status" className="rounded-2xl border border-line bg-surface p-6">
        <p className="font-medium">{loading ? m.workspace.loading : m.workspace.none}</p>
        <div className="sweep relative mt-4 h-1.5 overflow-hidden rounded-full bg-surface2" />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {loading && <p role="status" className="text-xs text-ink2">{m.workspace.loading}</p>}
      {page === "profile" && <ProfilePage />}
      {page === "experiences" && <FactsPage group="experience" />}
      {page === "education" && <FactsPage group="education" />}
      {page === "skills" && <SkillsPage />}
      {page === "offers" && <JobsPage />}
      {page === "adapt" && <AdaptPage />}
      {page === "history" && <HistoryPage />}
      {page === "review" && <ReviewPage />}
    </div>
  );
}


function Sidebar({ t, page, onNavigate }: { t: Dict; page: Page; onNavigate: (p: Page) => void }) {
  return (
    <nav aria-label={t.appName} className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-surface p-2 md:w-60 md:flex-col md:overflow-visible md:border-b-0 md:border-r md:p-4">
      <div className="hidden items-center gap-2 px-3 pb-5 pt-2 md:flex">
        <span aria-hidden="true" className="grid size-8 place-items-center rounded-lg bg-accent font-display text-sm font-bold text-accentink">M</span>
        <span className="font-display text-base font-semibold tracking-tight">ModularCV</span>
      </div>
      {PAGES.map((p) => (
        <button
          key={p.id}
          type="button"
          aria-current={page === p.id ? "page" : undefined}
          onClick={() => onNavigate(p.id)}
          className={
            "flex shrink-0 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors " +
            (page === p.id ? "bg-surface2 font-medium text-ink" : "text-ink2 hover:bg-surface2 hover:text-ink") +
            (p.id === "settings" ? " md:mt-auto" : "") +
            (p.id === "offers" ? " md:mt-3" : "") +
            (p.id === "history" ? " md:mt-3" : "")
          }
        >
          <Icon page={p.id} />
          <span className="whitespace-nowrap">{t.nav[p.id]}</span>
          {!p.ready && <span className="ml-auto hidden rounded bg-surface2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink2 md:inline">{t.soon}</span>}
        </button>
      ))}
    </nav>
  );
}

function NotImplemented({ t, title }: { t: Dict; title: string }) {
  return (
    <section className="rounded-2xl border border-dashed border-line p-10 text-center">
      <h2 className="font-display text-xl font-semibold">{title}</h2>
      <p className="mt-1 text-sm font-medium text-warning">{t.notImplemented}</p>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-ink2">{t.notImplementedBody}</p>
    </section>
  );
}

type Run = { state: "idle" } | { state: "running" } | { state: "done"; result: ValidationResult } | { state: "failed"; message: string };

function Dashboard({ t, m, workspace, onWorkspace, state, loading }: { t: Dict; m: Strings; workspace: string; onWorkspace: (p: string) => void; state: WorkspaceState | null; loading: boolean }) {
  const [draft, setDraft] = useState(workspace);
  const [manual, setManual] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [run, setRun] = useState<Run>({ state: "idle" });
  const [preparing, setPreparing] = useState(false);
  const running = run.state === "running";
  const desktop = isTauri();

  useEffect(() => setDraft(workspace), [workspace]);

  async function choose() {
    const picked = await pickFolder();
    if (picked) {
      onWorkspace(picked);
      setRun({ state: "idle" });
      setNote(null);
    }
  }

  async function useDemo(kind: DemoKind) {
    setPreparing(true);
    try {
      const demo = await prepareDemoWorkspace(kind);
      onWorkspace(demo.path);
      setNote(demo.created ? t.dashboard.demoReady : t.dashboard.demoExisting);
      setRun({ state: "idle" });
    } catch (e) {
      setRun({ state: "failed", message: String(e) });
    } finally {
      setPreparing(false);
    }
  }

  async function check() {
    if (!workspace.trim()) {
      setNote(t.dashboard.needPath);
      return;
    }
    setNote(null);
    setRun({ state: "running" });
    try {
      setRun({ state: "done", result: await validateWorkspace(workspace.trim()) });
    } catch (e) {
      setRun({ state: "failed", message: String(e) });
    }
  }

  return (
    <div className="space-y-8">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{t.dashboard.subtitle}</p>

      <section aria-labelledby="ws-title" className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
        <h2 id="ws-title" className="font-display text-lg font-semibold">{t.dashboard.workspace}</h2>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => void choose()} disabled={!desktop || running}>{m.workspace.choose}</Button>
          <Button onClick={() => void useDemo("valid")} disabled={preparing || running || !desktop}>{t.dashboard.useDemo}</Button>
          <Button onClick={() => void useDemo("invalid")} disabled={preparing || running || !desktop}>{t.dashboard.useDemoInvalid}</Button>
          <Button onClick={() => void useDemo("git")} disabled={preparing || running || !desktop} title={m.demoGit.hint}>{m.demoGit.button}</Button>
        </div>
        <div className="mt-4 rounded-lg border border-line bg-bg px-3 py-2" aria-live="polite">
          <p className="text-xs uppercase tracking-wide text-ink2">{t.dashboard.pathLabel}</p>
          <p className="mt-0.5 break-all font-mono text-sm">{workspace || m.workspace.none}</p>
          {workspace && state && <p className="mt-1 text-xs text-ink2">{loading ? m.workspace.loading : "✔ " + m.workspace.label}</p>}
        </div>
        <button type="button" onClick={() => setManual((v) => !v)} aria-expanded={manual} className="mt-3 cursor-pointer text-sm text-ink2 underline-offset-2 hover:underline">
          {manual ? m.workspace.manualHide : m.workspace.manual}
        </button>
        {manual && (
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) onWorkspace(draft.trim());
            }}
          >
            <label htmlFor="ws-path" className="sr-only">{t.dashboard.pathLabel}</label>
            <input id="ws-path" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t.dashboard.pathPlaceholder} spellCheck={false} autoComplete="off" className={inputCls + " mt-0 font-mono"} />
            <Button type="submit" disabled={!draft.trim()}>{m.workspace.open}</Button>
          </form>
        )}
        <p className="mt-3 text-xs leading-relaxed text-ink2">{t.dashboard.demoHint}</p>
        <p className="mt-1 text-xs leading-relaxed text-ink2">{m.demoGit.hint}</p>
        {note && <p role="status" className="mt-2 text-sm text-ink">{note}</p>}
        {!desktop && <p role="alert" className="mt-2 text-sm text-warning">{t.dashboard.notDesktop}</p>}
        <div className="mt-5 flex justify-end">
          <Button variant="primary" onClick={() => void check()} disabled={running || !desktop || !workspace}>
            {running ? t.dashboard.checking : t.dashboard.check}
          </Button>
        </div>
      </section>

      <section aria-labelledby="res-title" aria-live="polite">
        <h2 id="res-title" className="font-display mb-3 text-lg font-semibold">{t.result.title}</h2>
        {run.state === "idle" && (
          <div className="rounded-2xl border border-dashed border-line p-10 text-center">
            <p className="font-medium">{t.dashboard.emptyTitle}</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-ink2">{t.dashboard.emptyBody}</p>
          </div>
        )}
        {run.state === "running" && <Running t={t} />}
        {run.state === "failed" && <Banner tone="danger" title={t.outcome.process_failed} body={run.message} />}
        {run.state === "done" && <Result t={t} result={run.result} />}
      </section>
    </div>
  );
}

function Running({ t }: { t: Dict }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-6" role="status">
      <p className="font-medium">{t.result.runningTitle}</p>
      <p className="mt-1 font-mono text-xs text-ink2">{t.result.runningBody}</p>
      <div className="sweep relative mt-4 h-1.5 overflow-hidden rounded-full bg-surface2" />
    </div>
  );
}

const TONE: Record<string, string> = {
  success: "border-success/40 bg-successbg text-success",
  warning: "border-warning/40 bg-warningbg text-warning",
  danger: "border-danger/40 bg-dangerbg text-danger",
};

function Banner({ tone, title, body }: { tone: "success" | "warning" | "danger"; title: string; body?: string | null }) {
  return (
    <div role={tone === "success" ? "status" : "alert"} className={"rise rounded-2xl border p-5 " + TONE[tone]}>
      <p className="font-display text-lg font-semibold">{title}</p>
      {body && <p className="mt-1 text-sm leading-relaxed text-ink">{body}</p>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <dt className="text-xs uppercase tracking-wide text-ink2">{label}</dt>
      <dd className="font-display mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Result({ t, result }: { t: Dict; result: ValidationResult }) {
  const tone = toneOf(result.outcome);
  const report = result.report;
  const ok = isSuccess(result);
  const title = ok ? t.result.validTitle : result.outcome === "invalid" ? t.result.invalidTitle : t.outcome[result.outcome];
  const body = ok ? t.result.validBody : result.outcome === "invalid" ? t.result.invalidBody : (t.outcomeHelp[result.outcome] ?? result.detail);
  const extra = !ok && result.outcome !== "invalid" ? result.detail : null;
  const errors = report?.errors ?? [];
  const warnings = report?.warnings ?? [];
  const counts = useMemo(() => Object.entries(report?.counts ?? {}), [report]);

  return (
    <div className="space-y-5">
      <Banner tone={tone} title={title} body={body} />
      {extra && extra !== body && <p className="text-sm text-ink2">{extra}</p>}
      {report && (ok || result.outcome === "invalid") && (
        <dl className="rise grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label={t.result.facts} value={String(report.fact_count ?? "—")} />
          <Stat label={t.result.publishable} value={String(report.publishable ?? "—")} />
          <Stat label={t.result.exit} value={String(result.exit_code ?? "—")} />
          <Stat label={t.result.duration} value={`${result.duration_ms} ms`} />
        </dl>
      )}
      {counts.length > 0 && (
        <div className="rounded-xl border border-line bg-surface p-4">
          <h3 className="text-sm font-medium">{t.result.counts}</h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {counts.map(([k, v]) => (
              <li key={k} className="rounded-full border border-line bg-surface2 px-3 py-1 text-sm">
                {t.statusLabels[k] ?? k} <span className="font-semibold tabular-nums">{v}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {report && (errors.length > 0 || warnings.length > 0 || ok) && (
        <div className="grid gap-3 md:grid-cols-2">
          <DiagList t={t} title={t.result.errors} items={errors} tone="danger" />
          <DiagList t={t} title={t.result.warnings} items={warnings} tone="warning" />
        </div>
      )}
      {report?.factbase_sha256 && (
        <p className="text-xs text-ink2">
          {t.result.fingerprint}: <code className="font-mono">{shortHash(report.factbase_sha256)}</code>
        </p>
      )}
      {result.stderr_excerpt && (
        <details className="rounded-xl border border-line bg-surface p-4 text-sm">
          <summary className="cursor-pointer font-medium">{t.result.engineOutput}</summary>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-ink2">{result.stderr_excerpt}</pre>
        </details>
      )}
    </div>
  );
}

function DiagList({ t, title, items, tone }: { t: Dict; title: string; items: { code: string; line: number | null; message: string }[]; tone: "danger" | "warning" }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <h3 className="text-sm font-medium">{title} <span className="tabular-nums text-ink2">({items.length})</span></h3>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-ink2">{t.result.none}</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {items.map((d, i) => (
            <li key={i} className="text-sm">
              <code className={"font-mono text-xs " + (tone === "danger" ? "text-danger" : "text-warning")}>{d.code}</code>
              {d.line != null && <span className="text-xs text-ink2"> · {t.result.line} {d.line}</span>}
              <p className="text-ink2">{d.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <fieldset className="rounded-2xl border border-line bg-surface p-5">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      <div className="mt-1 flex flex-wrap gap-2">
        {options.map((o) => (
          <label key={o.id} className={"cursor-pointer rounded-lg border px-3.5 py-2 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent " + (value === o.id ? "border-accent bg-surface2 font-medium" : "border-line hover:bg-surface2")}>
            <input type="radio" name={label} value={o.id} checked={value === o.id} onChange={() => onChange(o.id)} className="sr-only" />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Settings({ t, themePref, langPref, onTheme, onLang }: { t: Dict; themePref: ThemePref; langPref: LangPref; onTheme: (v: ThemePref) => void; onLang: (v: LangPref) => void }) {
  return (
    <div className="space-y-5">
      <Segmented label={t.settings.theme} value={themePref} onChange={onTheme} options={[{ id: "system", label: t.settings.system }, { id: "light", label: t.settings.light }, { id: "dark", label: t.settings.dark }]} />
      <Segmented label={t.settings.language} value={langPref} onChange={onLang} options={[{ id: "system", label: t.settings.system }, { id: "fr", label: t.settings.french }, { id: "en", label: t.settings.english }]} />
      <DiagnosticsCard />
    </div>
  );
}
