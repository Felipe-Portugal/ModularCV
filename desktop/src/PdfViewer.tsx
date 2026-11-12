import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { adapter, openPdf } from "./bridge";
import { useApp } from "./ctx";
import { base64ToBytes, clampPage, clampZoom, formatBytes, sha256Hex } from "./packages";
import { Button, FailureNotice, Notice } from "./ui";
import type { AdapterFailure, PdfRead } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export type PdfTarget = { package: string } | { output: string };

type Loaded = { doc: pdfjs.PDFDocumentProxy; task: pdfjs.PDFDocumentLoadingTask; info: PdfRead; browserHash: string };

/**
 * Shows the exact bytes of a validated workspace PDF with pdf.js.
 *
 * The bytes come from the engine adapter (`pdf_read`), which only reads two fixed locations of the active workspace and
 * checks them as a PDF; nothing is loaded from a URL or a free path. The SHA-256 computed here on the received bytes is
 * compared with the engine's.
 */
export interface ViewerInfo {
  engineSha: string;
  browserSha: string;
  pages: number;
}

export default function PdfViewer({ target, exact, refreshKey = 0, onLoaded, onPageShown }: { target: PdfTarget; exact: "package" | "output"; refreshKey?: number; onLoaded?: (info: ViewerInfo | null) => void; onPageShown?: (page: number) => void }) {
  const { m, workspace } = useApp();
  const t = m.preview;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failure, setFailure] = useState<AdapterFailure | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [width, setWidth] = useState(0);
  const [openError, setOpenError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [applied, setApplied] = useState(1);
  const canvas = useRef<HTMLCanvasElement>(null);
  const cbLoaded = useRef(onLoaded);
  const cbShown = useRef(onPageShown);
  cbLoaded.current = onLoaded;
  cbShown.current = onPageShown;
  const box = useRef<HTMLDivElement>(null);
  const key = "package" in target ? "p:" + target.package : "o:" + target.output;

  useEffect(() => {
    let cancelled = false;
    let task: pdfjs.PDFDocumentLoadingTask | null = null;
    setLoaded(null);
    cbLoaded.current?.(null);
    setFailure(null);
    setRenderError(null);
    setPage(1);
    void (async () => {
      const res = await adapter<PdfRead>(workspace, "pdf_read", { ...target });
      if (cancelled) return;
      if (!res.ok) return setFailure(res);
      try {
        const bytes = base64ToBytes(res.base64 ?? "");
        const browserHash = await sha256Hex(bytes);
        task = pdfjs.getDocument({ data: bytes.slice() });
        const doc = await task.promise;
        if (cancelled) return;
        setLoaded({ doc, task, info: res, browserHash });
        cbLoaded.current?.({ engineSha: res.sha256, browserSha: browserHash, pages: doc.numPages });
      } catch (e) {
        if (!cancelled) setRenderError(String((e as Error)?.message ?? e));
      }
    })();
    return () => {
      cancelled = true;
      void task?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, key, refreshKey]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, [loaded]);

  useEffect(() => {
    if (!loaded || !canvas.current || !width) return;
    let cancelled = false;
    let renderTask: pdfjs.RenderTask | null = null;
    setRendering(true);
    void (async () => {
      try {
        const pdfPage = await loaded.doc.getPage(clampPage(page, loaded.doc.numPages));
        const natural = pdfPage.getViewport({ scale: 1 });
        const scale = zoom === "fit" ? Math.max(0.3, (width - 2) / natural.width) : zoom;
        setApplied(scale);
        const ratio = window.devicePixelRatio || 1;
        const viewport = pdfPage.getViewport({ scale: scale * ratio });
        const el = canvas.current;
        if (!el || cancelled) return;
        el.width = Math.floor(viewport.width);
        el.height = Math.floor(viewport.height);
        el.style.width = Math.floor(viewport.width / ratio) + "px";
        el.style.height = Math.floor(viewport.height / ratio) + "px";
        renderTask = pdfPage.render({ canvas: el, viewport });
        await renderTask.promise;
        if (!cancelled) {
          setRendering(false);
          cbShown.current?.(clampPage(page, loaded.doc.numPages));
        }
      } catch (e) {
        if ((e as Error)?.name === "RenderingCancelledException" || cancelled) return;
        setRenderError(String((e as Error)?.message ?? e));
        setRendering(false);
      }
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [loaded, page, zoom, width]);

  useEffect(() => () => void loaded?.task.destroy(), [loaded]);

  function step(delta: number) {
    setZoom((z) => clampZoom((z === "fit" ? applied : z) + delta));
  }

  async function external() {
    setOpenError(null);
    try {
      await openPdf(workspace, target);
    } catch (e) {
      setOpenError(String(e));
    }
  }

  async function copyHash() {
    if (!loaded) return;
    try {
      await navigator.clipboard.writeText(loaded.info.sha256);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable: the hash stays selectable on screen */
    }
  }

  if (failure) {
    const friendly = t.errors[failure.code];
    return friendly ? (
      <Notice tone="warning" title={friendly}>
        <code className="font-mono text-xs">{failure.code}</code>
      </Notice>
    ) : (
      <FailureNotice failure={failure} />
    );
  }
  if (renderError && !loaded) {
    return (
      <Notice tone="danger" title={t.renderFailed}>
        <code className="font-mono text-xs">{renderError.slice(0, 200)}</code>
      </Notice>
    );
  }
  if (!loaded) {
    return (
      <div role="status" className="rounded-xl border border-line bg-surface2 p-5 text-sm text-ink2">
        {t.loading}
        <div className="sweep relative mt-3 h-1.5 overflow-hidden rounded-full bg-bg" />
      </div>
    );
  }

  const pages = loaded.doc.numPages;
  const match = loaded.browserHash === loaded.info.sha256;
  const percent = Math.round(applied * 100);
  const label = t.canvasLabel.replace("{n}", String(page)).replace("{total}", String(pages));

  return (
    <div className="space-y-3">
      <div role="toolbar" aria-label={t.title} className="flex flex-wrap items-center gap-2">
        <Button aria-label={t.prev} title={t.prev} disabled={page <= 1} onClick={() => setPage((p) => clampPage(p - 1, pages))}>‹</Button>
        <label className="flex items-center gap-1.5 text-sm">
          <span className="sr-only">{t.page}</span>
          <input
            aria-label={t.page}
            inputMode="numeric"
            className="w-12 rounded-lg border border-line bg-bg px-2 py-1.5 text-center tabular-nums"
            value={page}
            onChange={(e) => setPage(clampPage(Number(e.target.value.replace(/\D/g, "")) || 1, pages))}
          />
          <span className="text-ink2" aria-hidden="true">{t.of} {pages}</span>
          <span className="sr-only">{t.of} {pages}</span>
        </label>
        <Button aria-label={t.next} title={t.next} disabled={page >= pages} onClick={() => setPage((p) => clampPage(p + 1, pages))}>›</Button>
        <span className="mx-1 hidden h-5 w-px bg-line sm:block" aria-hidden="true" />
        <Button aria-label={t.zoomOut} title={t.zoomOut} disabled={percent <= 50} onClick={() => step(-0.25)}>−</Button>
        <span className="w-12 text-center text-sm tabular-nums text-ink2" aria-label={t.zoomLevel}>{percent} %</span>
        <Button aria-label={t.zoomIn} title={t.zoomIn} disabled={percent >= 300} onClick={() => step(0.25)}>+</Button>
        <Button variant="ghost" aria-pressed={zoom === "fit"} onClick={() => setZoom("fit")}>{t.fit}</Button>
        <span className="ml-auto" />
        <Button onClick={() => void external()}>{t.openExternal}</Button>
      </div>
      {openError && <p role="alert" className="text-sm text-danger">{t.openFailed} {openError}</p>}

      <div
        ref={box}
        tabIndex={0}
        aria-label={t.title}
        onKeyDown={(e) => {
          if (e.key === "PageDown") setPage((p) => clampPage(p + 1, pages));
          if (e.key === "PageUp") setPage((p) => clampPage(p - 1, pages));
        }}
        className="max-h-[70vh] overflow-auto rounded-xl border border-line bg-surface2 p-1 focus-visible:outline-2 focus-visible:outline-accent"
      >
        <canvas ref={canvas} role="img" aria-label={label} className="mx-auto block bg-white shadow-sm" />
      </div>
      {rendering && <p role="status" className="text-xs text-ink2">{t.rendering}</p>}
      {renderError && <p role="alert" className="text-sm text-danger">{t.renderFailed} {renderError.slice(0, 160)}</p>}

      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-ink2">{t.hash}</dt>
        <dd className="flex min-w-0 flex-wrap items-center gap-2">
          <code className="break-all font-mono text-xs">{loaded.info.sha256}</code>
          <Button variant="ghost" onClick={() => void copyHash()}>{copied ? t.copied : t.copy}</Button>
        </dd>
        <dt className="text-ink2">{t.size}</dt>
        <dd className="tabular-nums">{formatBytes(loaded.info.bytes)} · {pages} {t.pages}</dd>
      </dl>
      {match ? (
        <p className="text-xs text-ink2">✔ {t.hashMatch}</p>
      ) : (
        <Notice tone="danger" title={t.hashMismatch} />
      )}
      <p className="text-xs text-ink2">{exact === "package" ? t.exact : t.exactOutput}</p>
    </div>
  );
}
