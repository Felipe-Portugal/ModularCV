import { describe, expect, it } from "vitest";
import { dictionaries, resolveLang } from "./i18n";
import type { Outcome, ValidationResult } from "./types";
import { inlineSpans, isSuccess, plural, shortHash, toneOf } from "./view";

const base: ValidationResult = {
  outcome: "valid",
  exit_code: 0,
  report: {
    status: "OK",
    file: "facts.md",
    fact_count: 9,
    counts: { CONFIRMED: 6 },
    publishable: 6,
    facts_source_sha256: "a".repeat(64),
    factbase_sha256: "b".repeat(64),
    errors: [],
    warnings: [],
  },
  detail: null,
  stderr_excerpt: null,
  duration_ms: 10,
};

describe("success is only a real engine verdict", () => {
  it("accepts a consistent valid result", () => expect(isSuccess(base)).toBe(true));
  it("rejects null", () => expect(isSuccess(null)).toBe(false));
  it("rejects a non-zero exit code", () => expect(isSuccess({ ...base, exit_code: 1 })).toBe(false));
  it("rejects a missing report", () => expect(isSuccess({ ...base, report: null })).toBe(false));
  it("rejects an INVALID report", () =>
    expect(isSuccess({ ...base, report: { ...base.report!, status: "INVALID" } })).toBe(false));
  it("rejects every non-valid outcome", () => {
    const others: Outcome[] = ["invalid", "config_error", "workspace_missing", "python_unavailable", "timeout", "process_failed", "invalid_output", "engine_not_found", "runtime_unavailable", "operation_not_allowed"];
    for (const outcome of others) expect(isSuccess({ ...base, outcome })).toBe(false);
  });
});

describe("tones", () => {
  it("only valid is success", () => {
    expect(toneOf("valid")).toBe("success");
    expect(toneOf("invalid")).toBe("warning");
    expect(toneOf("timeout")).toBe("danger");
  });
});

describe("i18n", () => {
  it("fr and en define the same keys", () => {
    const keys = (o: object, p = ""): string[] =>
      Object.entries(o).flatMap(([k, v]) => (typeof v === "object" && v ? keys(v, p + k + ".") : [p + k]));
    expect(keys(dictionaries.fr).sort()).toEqual(keys(dictionaries.en).sort());
  });
  it("resolves system language", () => {
    expect(resolveLang("system", "fr-FR")).toBe("fr");
    expect(resolveLang("system", "de-DE")).toBe("en");
    expect(resolveLang("en", "fr-FR")).toBe("en");
  });
  it("shortens hashes", () => {
    expect(shortHash(null)).toBe("—");
    expect(shortHash("a".repeat(64))).toBe("aaaaaaaa…aaaaaa");
  });
});

describe("inlineSpans", () => {
  it("renders bold and italic like the engine", () => {
    expect(inlineSpans("Built REST endpoints in **Python** for an _internal_ tool.")).toEqual([
      { text: "Built REST endpoints in ", bold: false, italic: false },
      { text: "Python", bold: true, italic: false },
      { text: " for an ", bold: false, italic: false },
      { text: "internal", bold: false, italic: true },
      { text: " tool.", bold: false, italic: false },
    ]);
  });
  it("keeps an underscore inside a word as text", () => {
    expect(inlineSpans("used snake_case names")).toEqual([{ text: "used snake_case names", bold: false, italic: false }]);
  });
  it("refuses an open marker so the raw text is shown", () => {
    expect(inlineSpans("**Python is open")).toBeNull();
  });
});

describe("plural", () => {
  it("uses the singular for 0 and 1 in French and only for 1 in English", () => {
    expect(plural("fr", 0, "{n} fait|{n} faits")).toBe("0 fait");
    expect(plural("fr", 1, "{n} fait|{n} faits")).toBe("1 fait");
    expect(plural("fr", 2, "{n} fait|{n} faits")).toBe("2 faits");
    expect(plural("en", 0, "{n} fact|{n} facts")).toBe("0 facts");
    expect(plural("en", 1, "{n} fact|{n} facts")).toBe("1 fact");
  });
  it("shows an unknown count with the plural form", () => {
    expect(plural("fr", null, "{n} page|{n} pages")).toBe("? pages");
  });
});
