import { useCallback, useEffect, useState } from "react";
import { diagnostics } from "./bridge";
import { useApp } from "./ctx";
import { Button, Card, FailureNotice, Pill } from "./ui";
import type { AdapterFailure, Diagnostics } from "./types";

function Row({ label, tone, status, children }: { label: string; tone: "success" | "warning" | "danger" | "neutral"; status: string; children?: React.ReactNode }) {
  return (
    <li className="rounded-xl border border-line p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <Pill tone={tone}>{status}</Pill>
      </div>
      {children && <div className="mt-1.5 text-sm leading-relaxed text-ink2">{children}</div>}
    </li>
  );
}

/** Dependencies are shown as they are: a missing one is never hidden and never installed by the application. */
export default function DiagnosticsCard() {
  const { m, workspace } = useApp();
  const t = m.diag;
  const [result, setResult] = useState<Diagnostics | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    const res = await diagnostics(workspace);
    setBusy(false);
    if (res.ok) setResult(res);
    else {
      setResult(null);
      setFailure(res);
    }
  }, [workspace]);

  useEffect(() => {
    void run();
  }, [run]);

  const d = result;
  return (
    <Card title={t.title} aside={<Button onClick={() => void run()} disabled={busy}>{busy ? t.running : t.run}</Button>}>
      <p className="text-sm leading-relaxed text-ink2">{t.intro}</p>
      {failure && (
        <div className="mt-4 space-y-2">
          <p role="alert" className="text-sm text-danger">{t.engineFailed}</p>
          <FailureNotice failure={failure} />
        </div>
      )}
      {!d && !failure && <p role="status" className="mt-4 text-sm text-ink2">{t.running}</p>}
      {d && (
        <ul className="mt-4 space-y-3" aria-label={t.title}>
          <Row label={t.engine} tone="success" status={d.mode === "embedded" ? t.engineEmbedded : t.engineDev}>
            {t.engineVersion.replace("{v}", d.engine.version).replace("{py}", d.engine.python)}
          </Row>
          <Row label={t.git} tone={d.git.status === "FOUND" ? "success" : "warning"} status={d.git.status === "FOUND" ? t.gitFound : t.gitAbsent}>
            {d.git.status === "FOUND" ? d.git.version : t.gitAbsentBody}
          </Row>
          <Row
            label={t.provenance}
            tone={d.provenance.status === "VERIFIED" ? "success" : d.provenance.status === "NOT_CHECKED" ? "neutral" : "warning"}
            status={d.provenance.status === "VERIFIED" ? t.provenanceVerified : d.provenance.status === "NOT_CHECKED" ? t.provenanceNone : t.provenanceNo}
          >
            {d.provenance.code && (
              <>
                {t.provenanceText[d.provenance.code] ?? ""} <code className="font-mono text-xs">{d.provenance.code}</code>
                {d.provenance.reason && <span> · {t.reasonText[d.provenance.reason] ?? d.provenance.reason}</span>}
              </>
            )}
          </Row>
          <Row label={t.latex} tone={d.latex.pdflatex === "FOUND" ? "success" : "warning"} status={d.latex.pdflatex === "FOUND" ? t.latexFound : t.latexAbsent}>
            {d.latex.pdflatex === "FOUND" ? [d.latex.distribution, d.latex.version].filter(Boolean).join(" · ") : t.latexAbsentBody}
          </Row>
          <Row label={t.compile} tone={d.latex.compile === "AVAILABLE" ? "success" : "warning"} status={d.latex.compile === "AVAILABLE" ? t.compileYes.split(" (")[0] : t.compileNo}>
            {d.latex.compile === "AVAILABLE" ? t.compileYes.slice(t.compileYes.indexOf("(")) : null}
          </Row>
        </ul>
      )}
      <p className="mt-4 text-xs text-ink2">{t.offline}{d && ` ${t.modeLabel}: ${d.mode}.`}</p>
    </Card>
  );
}
