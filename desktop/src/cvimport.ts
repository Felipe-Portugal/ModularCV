/**
 * Pure helpers of the CV import: the draft the user reviews, the request sent to the adapter (`cv_apply`),
 * and the rebuilding of text lines from the positioned fragments pdf.js returns.
 *
 * Nothing here decides anything about a fact: an entry is confirmed only by the box the user ticks.
 */

export type BlockKind = "experience" | "project" | "education" | "other";
export type FieldChoice = "skip" | "private" | "public";

/** What `cv_parse` returns. */
export interface CvProposal {
  ok: true;
  language: "fr" | "en";
  identity: { display_name: string; headline: string; location: string; email: string; phone: string; links: string[] } | null;
  blocks: { kind: BlockKind; title: string; subtitle: string; period: string; place: string; bullets: string[] }[];
  skills: { title: string; technical: boolean; items: string[] }[];
  unclassified: { section: string; text: string }[];
  sections_found: string[];
  lines: number;
}

export interface CvSource {
  ok: true;
  kind: "pdf" | "text";
  name: string;
  bytes: number;
  base64?: string;
  text?: string;
}

export interface CvApplied {
  ok: true;
  facts_added: number;
  confirmed: number;
  blocks_added: number;
  bullets_added: number;
  skills_added: number;
  parked: number;
  content_created: boolean;
  identity_updated: boolean;
}

export interface DraftLine {
  key: string;
  text: string;
  confirmed: boolean;
}

export interface DraftBlock {
  key: string;
  kind: BlockKind;
  title: string;
  subtitle: string;
  period: string;
  place: string;
  confirmed: boolean;
  bullets: DraftLine[];
}

export interface DraftCategory {
  key: string;
  title: string;
  technical: boolean;
  items: DraftLine[];
}

export const IDENTITY_FIELDS = ["display_name", "headline", "location", "email", "phone"] as const;
export type IdentityField = (typeof IDENTITY_FIELDS)[number];

export interface DraftIdentityField {
  value: string;
  choice: FieldChoice;
}

export interface DraftLink {
  key: string;
  label: string;
  value: string;
  choice: FieldChoice;
}

export interface Draft {
  identity: Record<IdentityField, DraftIdentityField>;
  links: DraftLink[];
  blocks: DraftBlock[];
  skills: DraftCategory[];
  unclassified: { key: string; section: string; text: string }[];
}

let counter = 0;
export function newKey(): string {
  counter += 1;
  return "k" + counter;
}

export function emptyBlock(kind: BlockKind = "experience"): DraftBlock {
  return { key: newKey(), kind, title: "", subtitle: "", period: "", place: "", confirmed: false, bullets: [] };
}

export function emptyLine(text = ""): DraftLine {
  return { key: newKey(), text, confirmed: false };
}

export function emptyDraft(): Draft {
  const identity = Object.fromEntries(IDENTITY_FIELDS.map((f) => [f, { value: "", choice: "skip" as FieldChoice }])) as Draft["identity"];
  return { identity, links: [], blocks: [], skills: [], unclassified: [] };
}

function linkLabel(value: string): string {
  const v = value.toLowerCase();
  if (v.includes("linkedin.")) return "LinkedIn";
  if (v.includes("github.")) return "GitHub";
  if (v.includes("gitlab.")) return "GitLab";
  return "Site";
}

/**
 * The reviewable draft of a proposal. Nothing is confirmed, and an identity value found in the document is
 * proposed as private: the user chooses what may be printed. The name already in the profile is left alone.
 */
export function proposalToDraft(proposal: CvProposal, currentName: string): Draft {
  const draft = emptyDraft();
  const found = proposal.identity;
  if (found) {
    for (const field of IDENTITY_FIELDS) {
      const value = (found[field] ?? "").trim();
      const same = field === "display_name" && value.toLowerCase() === currentName.trim().toLowerCase();
      draft.identity[field] = { value, choice: value && !same ? "private" : "skip" };
    }
    draft.links = (found.links ?? []).map((value) => ({ key: newKey(), label: linkLabel(value), value, choice: "private" as FieldChoice }));
  }
  draft.blocks = proposal.blocks.map((b) => ({
    key: newKey(), kind: b.kind, title: b.title, subtitle: b.subtitle, period: b.period, place: b.place, confirmed: false,
    bullets: b.bullets.map((text) => emptyLine(text)),
  }));
  draft.skills = proposal.skills.map((c) => ({ key: newKey(), title: c.title, technical: c.technical, items: c.items.map((text) => emptyLine(text)) }));
  draft.unclassified = proposal.unclassified.map((u) => ({ key: newKey(), ...u }));
  return draft;
}

export interface DraftCounts {
  /** Entries that will be written as facts. */
  entries: number;
  /** Entries the user confirmed. */
  confirmed: number;
  /** Entries that will be printed in a CV: confirmed, and inside a confirmed block. */
  placed: number;
  /** Blocks with lines but no title: they cannot be saved. */
  untitled: number;
}

export function countDraft(draft: Draft): DraftCounts {
  const out: DraftCounts = { entries: 0, confirmed: 0, placed: 0, untitled: 0 };
  for (const block of draft.blocks) {
    const lines = block.bullets.filter((l) => l.text.trim());
    if (!block.title.trim()) {
      if (lines.length) out.untitled += 1;
      continue;
    }
    out.entries += 1 + lines.length;
    if (block.confirmed) {
      out.confirmed += 1;
      out.placed += 1;
    }
    for (const line of lines) {
      if (line.confirmed) {
        out.confirmed += 1;
        if (block.confirmed) out.placed += 1;
      }
    }
  }
  for (const category of draft.skills) {
    if (!category.title.trim()) continue;
    for (const item of category.items.filter((i) => i.text.trim())) {
      out.entries += 1;
      if (item.confirmed) {
        out.confirmed += 1;
        out.placed += 1;
      }
    }
  }
  return out;
}

export function identityChosen(draft: Draft): number {
  return IDENTITY_FIELDS.filter((f) => draft.identity[f].choice !== "skip" && draft.identity[f].value.trim()).length
    + draft.links.filter((l) => l.choice !== "skip" && l.value.trim() && l.label.trim()).length;
}

const DATE = /^\d{4}(-\d{2}(-\d{2})?)?$/;
export function validDate(value: string): boolean {
  return DATE.test(value.trim());
}

/** The `cv_apply` request. Empty lines and untitled, empty blocks are left out; nothing else is altered. */
export function draftToRequest(draft: Draft, language: string, confirmedOn: string): Record<string, unknown> {
  const blocks = draft.blocks
    .filter((b) => b.title.trim())
    .map((b) => ({
      kind: b.kind, title: b.title, subtitle: b.subtitle, period: b.period, place: b.place, confirmed: b.confirmed,
      bullets: b.bullets.filter((l) => l.text.trim()).map((l) => ({ text: l.text, confirmed: l.confirmed })),
    }));
  const skills = draft.skills
    .filter((c) => c.title.trim() && c.items.some((i) => i.text.trim()))
    .map((c) => ({ title: c.title, technical: c.technical, items: c.items.filter((i) => i.text.trim()).map((i) => ({ text: i.text, confirmed: i.confirmed })) }));
  const identity: Record<string, unknown> = {};
  for (const field of IDENTITY_FIELDS) {
    const entry = draft.identity[field];
    if (entry.choice !== "skip" && entry.value.trim()) identity[field] = { value: entry.value, visibility: entry.choice };
  }
  const links = draft.links.filter((l) => l.choice !== "skip" && l.value.trim() && l.label.trim()).map((l) => ({ label: l.label, value: l.value, visibility: l.choice }));
  if (links.length) identity.links = links;
  const request: Record<string, unknown> = { language, blocks, skills };
  if (Object.keys(identity).length) request.identity = identity;
  if (confirmedOn.trim()) request.confirmed_on = confirmedOn.trim();
  return request;
}

// ---- text of a PDF ---------------------------------------------------------------------------------

/** A text fragment as pdf.js gives it: the string, its position (x, y from the bottom), its width and height. */
export interface TextFragment {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Rebuilds the lines of one page from positioned fragments: fragments on the same baseline form a line, lines are
 * read from top to bottom, and a gap between two fragments becomes one space. A two-column page is read line by
 * line across both columns: the user sees the resulting text and can correct it before it is analysed.
 */
export function linesFromFragments(fragments: TextFragment[]): string[] {
  const usable = fragments.filter((f) => f.str.trim());
  const rows: { y: number; height: number; items: TextFragment[] }[] = [];
  for (const fragment of [...usable].sort((a, b) => b.y - a.y || a.x - b.x)) {
    const tolerance = Math.max(2, (fragment.height || 10) * 0.45);
    const row = rows.find((r) => Math.abs(r.y - fragment.y) <= tolerance);
    if (row) row.items.push(fragment);
    else rows.push({ y: fragment.y, height: fragment.height || 10, items: [fragment] });
  }
  return rows
    .sort((a, b) => b.y - a.y)
    .map((row) => {
      let text = "";
      let end = Number.NEGATIVE_INFINITY;
      for (const item of row.items.sort((a, b) => a.x - b.x)) {
        const gap = item.x - end;
        const size = item.height || row.height || 10;
        if (text && gap > size * 0.18 && !text.endsWith(" ") && !item.str.startsWith(" ")) text += gap > size * 2.5 ? "   " : " ";
        text += item.str;
        end = item.x + item.width;
      }
      return text.replace(/[ \t]+$/g, "");
    })
    .filter((line) => line.trim());
}
