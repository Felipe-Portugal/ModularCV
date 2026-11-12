import { slugId } from "./forms";
import type { MatrixRow, MatrixState, OfferDocument, Priority } from "./types";

export interface RequirementForm {
  id: string;
  term: string;
  priority: Priority;
}

export interface OfferForm {
  job_key: string;
  title: string;
  company: string;
  description: string;
  language: string;
  employment_type: string;
  location: string;
  workplace_type: string;
  source_url: string;
  source_system: string;
  posted_on: string;
  requirements: RequirementForm[];
}

export const EMPLOYMENT: string[] = ["UNSPECIFIED", "INTERNSHIP", "PERMANENT", "FIXED_TERM", "PART_TIME"];

export function emptyOfferForm(): OfferForm {
  return {
    job_key: "", title: "", company: "", description: "", language: "auto", employment_type: "UNSPECIFIED",
    location: "", workplace_type: "", source_url: "", source_system: "", posted_on: "", requirements: [],
  };
}

export function offerToForm(doc: OfferDocument): OfferForm {
  return {
    job_key: doc.job_key, title: doc.title, company: doc.company, description: doc.description,
    language: doc.language ?? "auto", employment_type: doc.employment_type ?? "UNSPECIFIED",
    location: doc.location ?? "", workplace_type: doc.workplace_type ?? "", source_url: doc.source_url ?? "",
    source_system: doc.source_system ?? "", posted_on: doc.posted_on ?? "",
    requirements: (doc.requirements ?? []).map((r) => ({ id: r.id, term: r.term, priority: r.priority })),
  };
}

const norm = (v: string) => v.trim().replace(/\s+/g, " ");
const normDesc = (v: string) => v.replace(/\r\n/g, "\n").split("\n").map((l) => l.trimEnd()).join("\n").trim();

export function offerChanged(a: OfferForm, b: OfferForm): boolean {
  const keys = Object.keys(a).filter((k) => k !== "requirements" && k !== "description") as (keyof OfferForm)[];
  return (
    keys.some((k) => norm(a[k] as string) !== norm(b[k] as string)) ||
    normDesc(a.description) !== normDesc(b.description) ||
    JSON.stringify(a.requirements) !== JSON.stringify(b.requirements)
  );
}

/** Which required fields are still missing. The user must type them: nothing is guessed. */
export function missingRequired(form: OfferForm): string[] {
  return (["job_key", "title", "company", "description"] as const).filter((k) => (k === "description" ? normDesc(form[k]) === "" : norm(form[k]) === ""));
}

/** A suggestion for the job key, shown to the user who can accept or edit it. Never applied silently. */
export function suggestJobKey(title: string, company: string): string {
  return slugId([title, company].filter(Boolean).join(" ")).slice(0, 60);
}

export function offerCreateRequest(form: OfferForm): Record<string, unknown> {
  return { mode: "create", offer: offerPayload(form, true) };
}

export function offerUpdateRequest(file: string, sha: string, original: OfferForm, form: OfferForm): Record<string, unknown> {
  const all = offerPayload(form, false);
  const before = offerPayload(original, false);
  const changed = Object.fromEntries(Object.entries(all).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(before[k])));
  return { mode: "update", file, expected_sha256: sha, offer: changed };
}

function offerPayload(form: OfferForm, create: boolean): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    title: form.title, company: form.company, description: form.description, language: form.language,
    employment_type: form.employment_type, location: form.location, workplace_type: form.workplace_type,
    source_url: form.source_url, source_system: form.source_system, posted_on: form.posted_on,
    requirements: form.requirements.filter((r) => r.id.trim() || r.term.trim()),
  };
  if (create) payload.job_key = form.job_key;
  return payload;
}

// ---------------------------------------------------------------- matrix presentation

export const STATE_ORDER: MatrixState[] = ["DIRECT", "ADJACENT", "ABSENT", "FORBIDDEN_TO_CLAIM"];

/** Unmet REQUIRED rows first, then by priority and weight: required gaps are never pushed out of sight. */
export function sortRows(rows: MatrixRow[]): MatrixRow[] {
  const unmet = (r: MatrixRow) => (r.priority === "REQUIRED" && r.state !== "DIRECT" ? 0 : 1);
  return [...rows].sort(
    (a, b) =>
      unmet(a) - unmet(b) ||
      Number(b.priority === "REQUIRED") - Number(a.priority === "REQUIRED") ||
      b.weight - a.weight ||
      a.id.localeCompare(b.id),
  );
}

export function requiredGaps(rows: MatrixRow[]): MatrixRow[] {
  return rows.filter((r) => r.priority === "REQUIRED" && r.state !== "DIRECT");
}

export function countByState(rows: MatrixRow[]): Record<MatrixState, number> {
  const counts: Record<MatrixState, number> = { DIRECT: 0, ADJACENT: 0, ABSENT: 0, FORBIDDEN_TO_CLAIM: 0 };
  for (const r of rows) counts[r.state] += 1;
  return counts;
}

export function rowLabel(row: MatrixRow): string {
  return row.label ?? row.term_id ?? row.id;
}

/** Only a DIRECT row is demonstrated. ADJACENT is a neighbouring skill, never presented as proven. */
export function isDemonstrated(row: MatrixRow): boolean {
  return row.state === "DIRECT";
}
