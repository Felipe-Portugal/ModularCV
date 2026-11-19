import { describe, expect, it } from "vitest";
import { countDraft, draftToRequest, emptyBlock, emptyDraft, emptyLine, identityChosen, linesFromFragments, proposalToDraft, validDate } from "./cvimport";
import type { CvProposal } from "./cvimport";

const proposal: CvProposal = {
  ok: true,
  language: "en",
  identity: { display_name: "Jordan Example", headline: "Developer", location: "Exampleville", email: "jordan@example.com", phone: "", links: ["github.com/jordan-example"] },
  blocks: [{ kind: "experience", title: "Junior developer", subtitle: "Example Company", period: "2025 - 2026", place: "", bullets: ["Built REST endpoints.", "Wrote tests."] }],
  skills: [{ title: "Skills", technical: true, items: ["Python", "Git"] }],
  unclassified: [{ section: "Interests", text: "Climbing" }],
  sections_found: ["experience", "skills"],
  lines: 9,
};

describe("proposalToDraft", () => {
  it("confirms nothing and proposes identity values as private", () => {
    const draft = proposalToDraft(proposal, "Someone Else");
    expect(draft.blocks[0].confirmed).toBe(false);
    expect(draft.blocks[0].bullets.every((l) => !l.confirmed)).toBe(true);
    expect(draft.skills[0].items.every((i) => !i.confirmed)).toBe(true);
    expect(draft.identity.email).toEqual({ value: "jordan@example.com", choice: "private" });
    expect(draft.identity.phone.choice).toBe("skip");
    expect(draft.links[0]).toMatchObject({ label: "GitHub", choice: "private" });
    expect(draft.unclassified).toHaveLength(1);
  });

  it("leaves the name of the profile alone when the document repeats it", () => {
    expect(proposalToDraft(proposal, "jordan example").identity.display_name.choice).toBe("skip");
  });
});

describe("countDraft", () => {
  it("counts a line as placed only when it and its heading are confirmed", () => {
    const draft = proposalToDraft(proposal, "");
    expect(countDraft(draft)).toEqual({ entries: 5, confirmed: 0, placed: 0, untitled: 0 });
    draft.blocks[0].bullets[0].confirmed = true;
    expect(countDraft(draft)).toMatchObject({ confirmed: 1, placed: 0 });
    draft.blocks[0].confirmed = true;
    draft.skills[0].items[1].confirmed = true;
    expect(countDraft(draft)).toMatchObject({ confirmed: 3, placed: 3 });
  });

  it("reports a block with lines and no title, and ignores empty ones", () => {
    const draft = emptyDraft();
    draft.blocks = [emptyBlock(), { ...emptyBlock(), bullets: [emptyLine("A line")] }];
    expect(countDraft(draft)).toEqual({ entries: 0, confirmed: 0, placed: 0, untitled: 1 });
  });
});

describe("draftToRequest", () => {
  it("sends only what the user kept, with the confirmation flags as ticked", () => {
    const draft = proposalToDraft(proposal, "");
    draft.blocks[0].confirmed = true;
    draft.blocks[0].bullets[1].text = "   ";
    draft.blocks.push(emptyBlock());
    draft.identity.email.choice = "public";
    draft.identity.headline.choice = "skip";
    const request = draftToRequest(draft, "en", " 2026-01-10 ") as { blocks: { confirmed: boolean; bullets: unknown[] }[]; identity: Record<string, unknown>; confirmed_on: string; skills: unknown[] };
    expect(request.blocks).toHaveLength(1);
    expect(request.blocks[0].confirmed).toBe(true);
    expect(request.blocks[0].bullets).toEqual([{ text: "Built REST endpoints.", confirmed: false }]);
    expect(request.identity.email).toEqual({ value: "jordan@example.com", visibility: "public" });
    expect(request.identity.headline).toBeUndefined();
    expect(request.confirmed_on).toBe("2026-01-10");
    expect(identityChosen(draft)).toBe(4);
  });

  it("sends no date and no identity when there is none", () => {
    const request = draftToRequest({ ...emptyDraft(), blocks: [{ ...emptyBlock(), title: "T" }] }, "fr", "");
    expect(request).toEqual({ language: "fr", blocks: [{ kind: "experience", title: "T", subtitle: "", period: "", place: "", confirmed: false, bullets: [] }], skills: [] });
  });
});

describe("validDate", () => {
  it("accepts a year, a month or a day", () => {
    expect(["2026", "2026-01", "2026-01-31"].every(validDate)).toBe(true);
    expect(["", "26", "2026-1", "31/01/2026", "today"].some(validDate)).toBe(false);
  });
});

describe("linesFromFragments", () => {
  it("joins fragments of one baseline, top to bottom, with a space where there is a gap", () => {
    const lines = linesFromFragments([
      { str: "Python", x: 98, y: 500, width: 40, height: 10 },
      { str: "EXPERIENCE", x: 50, y: 700, width: 80, height: 12 },
      { str: "Built", x: 50, y: 500.5, width: 30, height: 10 },
      { str: "in", x: 84, y: 500, width: 10, height: 10 },
      { str: " ", x: 0, y: 600, width: 3, height: 10 },
      { str: "2025", x: 400, y: 700, width: 30, height: 12 },
    ]);
    expect(lines).toEqual(["EXPERIENCE   2025", "Built in Python"]);
  });

  it("does not add a space inside a word split in two fragments", () => {
    expect(linesFromFragments([{ str: "Deve", x: 10, y: 10, width: 20, height: 10 }, { str: "loper", x: 30.5, y: 10, width: 25, height: 10 }])).toEqual(["Developer"]);
  });
});
