import { describe, expect, it } from "vitest";
import { emptyFactForm, factFormChanged, factRequest, factToForm, needsConfirmation, profileChanges, profileToForm, sectionGroup, slugId, splitList } from "./forms";
import type { FactRec, ProfileDoc } from "./types";

const fact: FactRec = {
  id: "exp.a", status: "CONFIRMED", text: "Did A.", section: "experience", lang: null, confirmed_on: "2026-01",
  technologies: ["Python", "pytest"], capabilities: ["backend"], source: null, supersedes: null, note: null, extensions: {}, line: 3,
};

const doc: ProfileDoc = {
  languages: ["en", "fr"],
  default_language: "en",
  identity: {
    display_name: { value: "Jordan Example", visibility: "public" },
    phone: { value: "+1 555 0100", visibility: "private" },
    links: [{ label: "Portfolio", value: "https://example.org/j", visibility: "public" }],
  },
  families: {},
  policy: { never_publish_terms: ["salary"], forbidden_words: { en: ["guru"] }, require_confirmation_date: false },
};

describe("fact forms", () => {
  it("round-trips lists", () => {
    expect(splitList(" a ,b,, c  d ")).toEqual(["a", "b", "c d"]);
    expect(factToForm(fact).technologies).toBe("Python, pytest");
  });
  it("detects changes ignoring whitespace", () => {
    const f = factToForm(fact);
    expect(factFormChanged(f, { ...f, text: "Did  A. " })).toBe(false);
    expect(factFormChanged(f, { ...f, text: "Did B." })).toBe(true);
  });
  it("requires a decision to confirm, never for other statuses", () => {
    const f = factToForm(fact);
    expect(needsConfirmation(f, f)).toBe(false);
    expect(needsConfirmation(f, { ...f, text: "Did B." })).toBe(true);
    expect(needsConfirmation(f, { ...f, note: "just a note" })).toBe(false);
    const draft = { ...f, status: "NOT_CONFIRMED" as const };
    expect(needsConfirmation(draft, { ...draft, status: "CONFIRMED" })).toBe(true);
    expect(needsConfirmation(draft, draft)).toBe(false);
    expect(needsConfirmation(null, { ...emptyFactForm("skills"), status: "CONFIRMED" })).toBe(true);
  });
  it("a new fact defaults to NOT_CONFIRMED", () => expect(emptyFactForm("skills").status).toBe("NOT_CONFIRMED"));
  it("only sends a confirmation that the user decided", () => {
    const f = { ...factToForm(fact), status: "CONFIRMED" as const };
    expect(factRequest(f, "update", "sha", null)).not.toHaveProperty("confirm");
    expect(factRequest(f, "update", "sha", { decided: false, date: "2026-02-01" })).not.toHaveProperty("confirm");
    expect(factRequest(f, "update", "sha", { decided: true, date: "2026-02-01" })).toHaveProperty("confirm.confirmed_on", "2026-02-01");
    const draft = { ...f, status: "NOT_CONFIRMED" as const };
    expect(factRequest(draft, "update", "sha", { decided: true, date: "2026-02-01" })).not.toHaveProperty("confirm");
  });
  it("slugs ids and groups sections", () => {
    expect(slugId("Édu Master 2!")).toBe("edu-master-2");
    expect(sectionGroup("education")).toBe("education");
    expect(sectionGroup("projects")).toBe("experience");
    expect(sectionGroup(null)).toBe("experience");
  });
});

describe("profile forms", () => {
  it("no change, no payload", () => {
    const f = profileToForm(doc);
    expect(profileChanges(f, structuredClone(f))).toEqual({});
  });
  it("sends only what changed", () => {
    const f = profileToForm(doc);
    const g = structuredClone(f);
    g.identity.phone.visibility = "public";
    g.requireDate = true;
    g.forbidden.fr = "gourou\n\nmaître";
    expect(profileChanges(f, g)).toEqual({
      identity: { phone: { value: "+1 555 0100", visibility: "public" } },
      policy: { require_confirmation_date: true, forbidden_words: { en: ["guru"], fr: ["gourou", "maître"] } },
    });
  });
  it("missing optional identity fields default to private", () => {
    expect(profileToForm(doc).identity.email).toEqual({ value: "", visibility: "private" });
  });
});
