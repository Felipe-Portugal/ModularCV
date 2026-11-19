import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { linesFromFragments } from "./cvimport";
import type { TextFragment } from "./cvimport";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const MAX_PAGES = 12;

/**
 * The text of a PDF the user picked, read locally with pdf.js: no rendering, no network, nothing executed.
 * A scanned document (images only) has no text: the result is then empty and the caller says so.
 */
export async function pdfToText(bytes: Uint8Array): Promise<string> {
  const task = pdfjs.getDocument({ data: bytes.slice() });
  try {
    const doc = await task.promise;
    const pages: string[] = [];
    for (let number = 1; number <= Math.min(doc.numPages, MAX_PAGES); number += 1) {
      const page = await doc.getPage(number);
      const content = await page.getTextContent();
      const fragments: TextFragment[] = [];
      for (const item of content.items) {
        if (!("str" in item)) continue;
        fragments.push({ str: item.str, x: item.transform[4], y: item.transform[5], width: item.width, height: item.height });
      }
      pages.push(linesFromFragments(fragments).join("\n"));
    }
    return pages.join("\n");
  } finally {
    await task.destroy();
  }
}
