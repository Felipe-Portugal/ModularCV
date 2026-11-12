import type { FactRec, FactStatus, IdentityEntry, LinkEntry, ProfileDoc, Visibility } from "./types";

// ---------------------------------------------------------------- facts

export interface FactForm {
  id: string;
  status: FactStatus;
  text: string;
  section: string;
  lang: string;
  confirmed_on: string;
  technologies: string;
  capabilities: string;
  source: string;
  supersedes: string;
  note: string;
}

export function splitList(value: string): string[] {
  return value
    .split(",")
    .map((x) => x.trim().replace(/\s+/g, " "))
    .filter(Boolean);
}

export function factToForm(fact: FactRec): FactForm {
  return {
    id: fact.id,
    status: fact.status,
    text: fact.text,
    section: fact.section ?? "",
    lang: fact.lang ?? "",
    confirmed_on: fact.confirmed_on ?? "",
    technologies: fact.technologies.join(", "),
    capabilities: fact.capabilities.join(", "),
    source: fact.source ?? "",
    supersedes: fact.supersedes ?? "",
    note: fact.note ?? "",
  };
}

export function emptyFactForm(section: string): FactForm {
  return { id: "", status: "NOT_CONFIRMED", text: "", section, lang: "", confirmed_on: "", technologies: "", capabilities: "", source: "", supersedes: "", note: "" };
}

const norm = (v: string) => v.trim().replace(/\s+/g, " ");

export function factFormChanged(original: FactForm, current: FactForm): boolean {
  return (Object.keys(original) as (keyof FactForm)[]).some((k) => norm(original[k]) !== norm(current[k]));
}

/**
 * UI hint only: the engine adapter is the authority. True when saving would
 * (re)confirm the fact, so the user must take an explicit, dated decision.
 */
export function needsConfirmation(original: FactForm | null, current: FactForm): boolean {
  if (current.status !== "CONFIRMED") return false;
  if (!original || original.status !== "CONFIRMED") return true;
  return (["text", "technologies", "capabilities", "source", "supersedes"] as const).some((k) => norm(original[k]) !== norm(current[k]));
}

export function slugId(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9.\-]+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "");
}

export function factRequest(
  form: FactForm,
  mode: "update" | "create",
  expectedSha: string,
  confirmation: { decided: boolean; date: string } | null,
): Record<string, unknown> {
  const request: Record<string, unknown> = {
    mode,
    expected_sha256: expectedSha,
    fact: {
      id: form.id.trim(),
      status: form.status,
      text: form.text,
      section: form.section,
      lang: form.lang || null,
      confirmed_on: form.confirmed_on || null,
      technologies: splitList(form.technologies),
      capabilities: splitList(form.capabilities),
      source: form.source || null,
      supersedes: form.supersedes || null,
      note: form.note || null,
    },
  };
  if (confirmation?.decided && form.status === "CONFIRMED") request.confirm = { confirmed_on: confirmation.date.trim() };
  return request;
}

export function sectionGroup(sectionId: string | null): "education" | "skills" | "experience" {
  if (sectionId === "education") return "education";
  if (sectionId === "skills") return "skills";
  return "experience";
}

// ---------------------------------------------------------------- profile

export const IDENTITY_FIELDS = ["display_name", "headline", "location", "email", "phone"] as const;
export type IdentityName = (typeof IDENTITY_FIELDS)[number];

export interface ProfileForm {
  identity: Record<IdentityName, { value: string; visibility: Visibility }>;
  links: { label: string; value: string; visibility: Visibility }[];
  defaultLanguage: string;
  requireDate: boolean;
  never: string;
  omit: string;
  forbidden: Record<string, string>;
}

const lines = (items: string[] | undefined) => (items ?? []).join("\n");
export const splitLines = (value: string): string[] => value.split("\n").map(norm).filter(Boolean);

export function profileToForm(doc: ProfileDoc): ProfileForm {
  const identity = {} as ProfileForm["identity"];
  for (const name of IDENTITY_FIELDS) {
    const entry = doc.identity[name] as IdentityEntry | undefined;
    identity[name] = { value: entry?.value ?? "", visibility: entry?.visibility ?? "private" };
  }
  const forbidden: Record<string, string> = {};
  for (const lang of doc.languages) forbidden[lang] = lines(doc.policy?.forbidden_words?.[lang]);
  return {
    identity,
    links: (doc.identity.links ?? []).map((l: LinkEntry) => ({ label: l.label ?? "", value: l.value, visibility: l.visibility })),
    defaultLanguage: doc.default_language ?? doc.languages[0] ?? "",
    requireDate: doc.policy?.require_confirmation_date ?? false,
    never: lines(doc.policy?.never_publish_terms),
    omit: lines(doc.policy?.omit_by_default_terms),
    forbidden,
  };
}

export function profileChanged(original: ProfileForm, current: ProfileForm): boolean {
  return JSON.stringify(profileChanges(original, current)) !== "{}";
}

/** Only the parts the user changed; the adapter merges them into the untouched document. */
export function profileChanges(original: ProfileForm, current: ProfileForm): Record<string, unknown> {
  const out: Record<string, Record<string, unknown> | string> = {};
  const identity: Record<string, unknown> = {};
  for (const name of IDENTITY_FIELDS) {
    const a = original.identity[name];
    const b = current.identity[name];
    if (norm(a.value) !== norm(b.value) || a.visibility !== b.visibility) identity[name] = { value: b.value, visibility: b.visibility };
  }
  if (JSON.stringify(original.links) !== JSON.stringify(current.links)) identity.links = current.links;
  if (Object.keys(identity).length) out.identity = identity;
  if (original.defaultLanguage !== current.defaultLanguage) out.default_language = current.defaultLanguage;
  const policy: Record<string, unknown> = {};
  if (original.requireDate !== current.requireDate) policy.require_confirmation_date = current.requireDate;
  if (original.never !== current.never) policy.never_publish_terms = splitLines(current.never);
  if (original.omit !== current.omit) policy.omit_by_default_terms = splitLines(current.omit);
  if (JSON.stringify(original.forbidden) !== JSON.stringify(current.forbidden)) {
    policy.forbidden_words = Object.fromEntries(Object.entries(current.forbidden).map(([k, v]) => [k, splitLines(v)]));
  }
  if (Object.keys(policy).length) out.policy = policy;
  return out;
}

export function today(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
