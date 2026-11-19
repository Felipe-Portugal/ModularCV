import type { Outcome, ValidationResult } from "./types";

export type Tone = "success" | "danger" | "warning";

/** Only `valid` is success; everything else is shown as a problem. */
export function toneOf(outcome: Outcome): Tone {
  if (outcome === "valid") return "success";
  if (outcome === "invalid" || outcome === "config_error") return "warning";
  return "danger";
}

/** Success needs a real engine verdict: outcome, exit code and report status must all agree. */
export function isSuccess(result: ValidationResult | null): boolean {
  return !!result && result.outcome === "valid" && result.exit_code === 0 && result.report?.status === "OK";
}

export function shortHash(hash: string | null): string {
  return hash ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : "—";
}

export interface InlineSpan {
  text: string;
  bold: boolean;
  italic: boolean;
}

const WORD = /[\p{L}\p{N}]/u;

/** Spans of a ResumeContent-v1 text with `**bold**` and `_italic_`, following the engine's `assemble.inline_spans`.
 * An underscore inside a word (`snake_case`) is plain text. Null when a marker is left open: show the raw text. */
export function inlineSpans(text: string): InlineSpan[] | null {
  const spans: InlineSpan[] = [];
  let buffer = "";
  let bold = false;
  let italic = false;
  const flush = () => {
    if (buffer) spans.push({ text: buffer, bold, italic });
    buffer = "";
  };
  const chars = Array.from(text);
  let i = 0;
  while (i < chars.length) {
    if (chars[i] === "*" && chars[i + 1] === "*") {
      flush();
      bold = !bold;
      i += 2;
      continue;
    }
    if (chars[i] === "_") {
      const before = i ? chars[i - 1] : "";
      const after = i + 1 < chars.length ? chars[i + 1] : "";
      const opener = (!before || !WORD.test(before)) && !!after && !/\s/.test(after) && after !== "_";
      const closer = !!before && !/\s/.test(before) && before !== "_" && (!after || !WORD.test(after));
      if ((italic && closer) || (!italic && opener)) {
        flush();
        italic = !italic;
        i += 1;
        continue;
      }
    }
    buffer += chars[i];
    i += 1;
  }
  flush();
  return bold || italic ? null : spans;
}

/** The form of `"{n} page|{n} pages"` that fits `n` in `lang` (French: 0 and 1 take the singular). An unknown count shows "?". */
export function plural(lang: string, n: number | null | undefined, forms: string): string {
  const [one, other = one] = forms.split("|");
  if (n == null) return other.replace("{n}", "?");
  return (new Intl.PluralRules(lang).select(n) === "one" ? one : other).replace("{n}", String(n));
}
