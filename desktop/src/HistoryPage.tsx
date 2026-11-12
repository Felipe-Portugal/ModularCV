import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { adapter, openPdf } from "./bridge";
import { useApp } from "./ctx";
import { SELECTED_PACKAGE_KEY, explain, verdictTone } from "./packages";
import { Button, Card, FailureNotice, Notice, Pill } from "./ui";
import type { AdapterFailure, OutputsList, PackageRow, PackagesList } from "./types";

const PdfViewer = lazy(() => import("./PdfViewer"));

export default function HistoryPage() {
  const { m, workspace, navigate } = useApp();
  const t = m.history;
  const [list, setList] = useState<PackagesList | null>(null);
  const [outputs, setOutputs] = useState<OutputsList["files"]>([]);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    const [res, out] = await Promise.all([adapter<PackagesList>(workspace, "packages_list", {}), adapter<OutputsList>(workspace, "outputs_list", {})]);
    setBusy(false);
    if (!res.ok) return setFailure(res);
    setList(res);
    if (out.ok) setOutputs(out.files.filter((f) => f.kind === "pdf"));
  }, [workspace]);

  // statuses are recomputed by the engine each time the page opens
  useEffect(() => {
    void load();
  }, [load]);

  function open(name: string) {
    try {
      localStorage.setItem(SELECTED_PACKAGE_KEY, name);
    } catch {
      /* optional convenience */
    }
    navigate("review");
  }

  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{t.intro}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => void load()} disabled={busy}>{busy ? t.refreshing : t.refresh}</Button>
        {list && <span className="text-sm text-ink2">{t.count.replace("{n}", String(list.total))}</span>}
      </div>
      {failure && <FailureNotice failure={failure} />}
      {!list && !failure && <p role="status" className="text-sm text-ink2">{m.workspace.loading}</p>}

      {list && list.packages.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center">
          <p className="font-display text-lg font-semibold">{t.none}</p>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink2">{t.noneBody}</p>
          <Button variant="primary" className="mt-5" onClick={() => navigate("adapt")}>{t.goAdapt}</Button>
        </div>
      )}

      {list && list.packages.length > 0 && (
        <ul className="space-y-3">
          {list.packages.map((p) => <PackageCard key={p.name} row={p} onOpen={() => open(p.name)} />)}
        </ul>
      )}
      {list?.truncated && <p className="text-xs text-ink2">{t.truncated}</p>}
      {list && list.packages.length > 0 && <p className="text-xs text-ink2">{t.noDates}</p>}

      <Card title={t.outputsTitle}>
        <p className="text-sm text-ink2">{t.outputsBody}</p>
        {outputs.length === 0 ? (
          <p className="mt-3 text-sm text-ink2">{t.outputsNone}</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {outputs.map((f) => {
              const base = f.file.replace(/^out\//, "").replace(/\.pdf$/, "");
              const shown = preview === base;
              return (
                <li key={f.file} className="rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <code className="font-mono text-sm">{f.file}</code>
                    <div className="flex gap-2">
                      <Button aria-expanded={shown} onClick={() => setPreview(shown ? null : base)}>{shown ? t.hidePreview : t.preview}</Button>
                      <Button variant="ghost" onClick={() => void openPdf(workspace, { output: base }).catch(() => undefined)}>{t.openPdf}</Button>
                    </div>
                  </div>
                  {shown && (
                    <div className="mt-3">
                      <Suspense fallback={<p role="status" className="text-sm text-ink2">{m.preview.loading}</p>}>
                        <PdfViewer target={{ output: base }} exact="output" />
                      </Suspense>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function PackageCard({ row, onOpen }: { row: PackageRow; onOpen: () => void }) {
  const { m, workspace } = useApp();
  const t = m.history;
  const [openError, setOpenError] = useState<string | null>(null);
  if (!row.readable) {
    return (
      <li className="rounded-2xl border border-danger/40 bg-dangerbg p-4">
        <p className="font-medium"><code className="font-mono">{row.name}</code> · {t.unreadable}</p>
        <p className="mt-1 text-sm text-ink2">{t.unreadableBody}</p>
        <p className="mt-1 text-xs"><code className="font-mono">{row.code ?? ""}</code>{row.state ? <> · <Pill tone={verdictTone(row.state.status)}>{m.review.verdict[row.state.status] ?? row.state.status}</Pill></> : null}</p>
      </li>
    );
  }
  const status = row.state?.status ?? "";
  const reasons = row.state?.reasons ?? [];
  return (
    <li className="rise rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-mono text-sm font-medium">{row.name}</p>
          <p className="mt-0.5 text-sm text-ink2">{t.offer}: <code className="font-mono text-xs">{row.job_key}</code></p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill>{row.family}</Pill>
          <Pill>{row.language}</Pill>
          {row.document?.available ? (
            <Pill tone="success">{t.pdfAvailable}{row.document.pages != null ? ` · ${row.document.pages} ${t.pagesLabel}` : ""}</Pill>
          ) : (
            <Pill tone="warning">{t.pdfAbsent}</Pill>
          )}
          <span title={reasons.join(", ")}><Pill tone={verdictTone(status)}>{m.review.verdict[status] ?? status ?? "?"}</Pill></span>
        </div>
      </div>
      {reasons.length > 0 && (
        <p className="mt-2 text-sm text-ink2">
          {explain(m.review.reasonText, reasons[0], reasons[0])}
          {reasons.length > 1 && <span className="text-xs"> {t.reasonMore.replace("{n}", String(reasons.length - 1))}</span>}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" onClick={onOpen}>{t.detail}</Button>
        <Button disabled={!row.document?.available} onClick={() => void openPdf(workspace, { package: row.name }).then(() => setOpenError(null)).catch((e) => setOpenError(String(e)))}>{t.openPdf}</Button>
      </div>
      {openError && <Notice tone="danger" title={m.preview.openFailed}>{openError}</Notice>}
    </li>
  );
}
