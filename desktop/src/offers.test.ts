import { describe, expect, it } from "vitest";
import { countByState, emptyOfferForm, isDemonstrated, missingRequired, offerChanged, offerCreateRequest, offerToForm, offerUpdateRequest, requiredGaps, sortRows, suggestJobKey } from "./offers";
import type { MatrixRow, OfferDocument } from "./types";

const row = (over: Partial<MatrixRow>): MatrixRow => ({
  id: "req.x", term_id: "x", kind: "capability", label: null, priority: "REQUIRED", state: "DIRECT", reasons: [], forbidden_by: [],
  evidence: [], sources: [], weight: 1, unpublished_fact_ids: [], ...over,
});

const doc: OfferDocument = {
  job_key: "example-job", title: "Backend intern", company: "Example Co (fictional)", description: "Requirements:\n- Python",
  language: "en", requirements: [{ id: "must-python", term: "Python", priority: "REQUIRED" }],
};

describe("offer forms", () => {
  it("requires user-typed fields, never fills them", () => {
    expect(missingRequired(emptyOfferForm())).toEqual(["job_key", "title", "company", "description"]);
    expect(missingRequired(offerToForm(doc))).toEqual([]);
    expect(emptyOfferForm().description).toBe("");
  });
  it("suggests a key without applying it", () => {
    expect(suggestJobKey("Développeur Backend", "Example Co")).toBe("developpeur-backend-example-co");
    expect(emptyOfferForm().job_key).toBe("");
  });
  it("detects changes and ignores whitespace noise", () => {
    const f = offerToForm(doc);
    expect(offerChanged(f, { ...f, title: "  Backend   intern " })).toBe(false);
    expect(offerChanged(f, { ...f, description: "Requirements:\r\n- Python  " })).toBe(false);
    expect(offerChanged(f, { ...f, title: "Other" })).toBe(true);
    expect(offerChanged(f, { ...f, requirements: [] })).toBe(true);
  });
  it("create sends the key, update sends only changes", () => {
    const f = offerToForm(doc);
    expect((offerCreateRequest(f).offer as Record<string, unknown>).job_key).toBe("example-job");
    const req = offerUpdateRequest("example-job.json", "sha", f, { ...f, title: "New" });
    expect(req).toEqual({ mode: "update", file: "example-job.json", expected_sha256: "sha", offer: { title: "New" } });
    expect((req.offer as Record<string, unknown>).job_key).toBeUndefined();
  });
});

describe("matrix presentation", () => {
  const rows = [
    row({ id: "a", state: "DIRECT", priority: "PREFERRED", weight: 9 }),
    row({ id: "b", state: "ABSENT", priority: "REQUIRED", weight: 1 }),
    row({ id: "c", state: "ADJACENT", priority: "REQUIRED", weight: 2 }),
    row({ id: "d", state: "FORBIDDEN_TO_CLAIM", priority: "PREFERRED", weight: 3 }),
    row({ id: "e", state: "DIRECT", priority: "REQUIRED", weight: 4 }),
  ];
  it("puts unmet required requirements first", () => {
    expect(sortRows(rows).slice(0, 2).map((r) => r.id)).toEqual(["c", "b"]);
    expect(requiredGaps(rows).map((r) => r.id).sort()).toEqual(["b", "c"]);
  });
  it("never hides required gaps from the counts", () => {
    expect(countByState(rows)).toEqual({ DIRECT: 2, ADJACENT: 1, ABSENT: 1, FORBIDDEN_TO_CLAIM: 1 });
  });
  it("only DIRECT is demonstrated", () => {
    expect(rows.filter(isDemonstrated).map((r) => r.id)).toEqual(["a", "e"]);
  });
});
