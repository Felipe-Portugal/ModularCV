/** Mirrors the Rust `ValidationResult` (src-tauri/src/engine.rs). */
export type Outcome =
  | "valid"
  | "invalid"
  | "config_error"
  | "workspace_missing"
  | "operation_not_allowed"
  | "python_unavailable"
  | "engine_not_found"
  | "timeout"
  | "process_failed"
  | "invalid_output";

export interface Diagnostic {
  code: string;
  line: number | null;
  message: string;
}

export interface FactsReport {
  status: string;
  file: string;
  fact_count: number | null;
  counts: Record<string, number> | null;
  publishable: number | null;
  facts_source_sha256: string | null;
  factbase_sha256: string | null;
  errors: Diagnostic[];
  warnings: Diagnostic[];
}

export interface ValidationResult {
  outcome: Outcome;
  exit_code: number | null;
  report: FactsReport | null;
  detail: string | null;
  stderr_excerpt: string | null;
  duration_ms: number;
}

export interface DemoWorkspace {
  path: string;
  created: boolean;
}

export type DemoKind = "valid" | "invalid" | "git";
export type Lang = "fr" | "en";
export type LangPref = Lang | "system";
export type ThemePref = "system" | "light" | "dark";
export type Page = "dashboard" | "profile" | "experiences" | "education" | "skills" | "offers" | "adapt" | "history" | "review" | "settings";

// ---- structured adapter (desktop/adapter/mcv_adapter.py) -------------------------------------

export interface Problem {
  code: string;
  message: string;
  path: string | null;
  file?: string;
}

export interface AdapterFailure {
  ok: false;
  code: string;
  message: string;
  details: Problem[];
}

export type FactStatus = "CONFIRMED" | "DERIVED" | "NOT_CONFIRMED" | "WITHDRAWN";

export interface FactRec {
  id: string;
  status: FactStatus;
  text: string;
  section: string | null;
  lang: string | null;
  confirmed_on: string | null;
  technologies: string[];
  capabilities: string[];
  source: string | null;
  supersedes: string | null;
  note: string | null;
  extensions: Record<string, string>;
  line: number;
}

export interface SectionRec {
  id: string;
  title: string;
  line: number;
}

export type Visibility = "public" | "private";
export interface IdentityEntry {
  value: string;
  visibility: Visibility;
}
export interface LinkEntry extends IdentityEntry {
  label?: string;
}

export interface ProfileDoc {
  languages: string[];
  default_language?: string;
  identity: Record<string, IdentityEntry | LinkEntry[]> & { links?: LinkEntry[] };
  families: Record<string, { label?: string; languages?: string[]; core_skills?: string[]; clusters?: string[]; page_target?: number }>;
  policy?: {
    never_publish_terms?: string[];
    omit_by_default_terms?: string[];
    forbidden_words?: Record<string, string[]>;
    require_confirmation_date?: boolean;
  };
}

export interface SkillItem {
  id: string;
  text: Record<string, string>;
  technologies: string[];
  supports: { id: string; status: FactStatus | null }[];
}
export interface SkillCategory {
  id: string;
  title: Record<string, string>;
  items: SkillItem[];
}

export interface WorkspaceState {
  ok: true;
  root: string;
  files: Record<string, string>;
  require_confirmation_date: boolean;
  facts: {
    present: boolean;
    valid?: boolean;
    source_sha256?: string;
    errors: Problem[];
    warnings?: Problem[];
    sections?: SectionRec[];
    facts?: FactRec[];
    counts?: Record<string, number>;
  };
  profile: {
    present: boolean;
    valid?: boolean;
    source_sha256?: string;
    errors: Problem[];
    warnings?: Problem[];
    data?: ProfileDoc | null;
  };
  content: {
    present: boolean;
    valid?: boolean;
    source_sha256?: string;
    errors: Problem[];
    warnings?: Problem[];
    skills?: SkillCategory[];
  };
}

export interface SaveOk {
  ok: true;
  message: string;
  downstream: Problem[];
}

export type Result<T> = T | AdapterFailure;

// ---- offers, matrix, plan, generation ----------------------------------------------------------

export type Employment = "INTERNSHIP" | "PERMANENT" | "FIXED_TERM" | "PART_TIME" | "UNSPECIFIED";
export type MatrixState = "DIRECT" | "ADJACENT" | "ABSENT" | "FORBIDDEN_TO_CLAIM";
export type Priority = "REQUIRED" | "PREFERRED";

export interface OfferSummary {
  file: string;
  sha256: string | null;
  valid: boolean;
  errors: Problem[];
  job_key?: string | null;
  title?: string | null;
  company?: string | null;
  language?: string | null;
  employment_type?: string | null;
  location?: string | null;
  workplace_type?: string | null;
  source_url?: string | null;
  posted_on?: string | null;
  description_chars?: number;
  requirements?: number;
}

export interface OffersList {
  ok: true;
  folder: string;
  offers: OfferSummary[];
  truncated: boolean;
}

export interface OfferDocument {
  job_key: string;
  title: string;
  company: string;
  description: string;
  language?: string;
  employment_type?: string;
  location?: string;
  workplace_type?: string;
  source_url?: string;
  source_system?: string;
  posted_on?: string;
  requirements?: { id: string; term: string; priority: Priority }[];
  [extra: string]: unknown;
}

export interface OfferRead {
  ok: true;
  file: string;
  sha256: string;
  valid: boolean;
  errors: Problem[];
  warnings: Problem[];
  document: OfferDocument | null;
}

export interface OfferSaved {
  ok: true;
  file: string;
  sha256: string;
}

export interface OfferImported {
  ok: true;
  kind: "offer" | "text";
  file?: string;
  text?: string;
}

export interface FamilyOption {
  id: string;
  label: string | null;
  languages: string[];
  page_target: number | null;
}

export interface AdaptOptions {
  ok: true;
  families: FamilyOption[];
  default_language: string;
  offer_language?: { language: string | null; method: string | null; declared: string };
}

export interface Evidence {
  type: string;
  id: string;
  relation: "DIRECT" | "ADJACENT";
  via: string | null;
  facts: string[];
}

export interface MatrixRow {
  id: string;
  term_id: string | null;
  kind: string | null;
  label: string | null;
  priority: Priority;
  state: MatrixState;
  reasons: string[];
  forbidden_by: string[];
  evidence: Evidence[];
  sources: string[];
  weight: number;
  unpublished_fact_ids: string[];
}

export interface Matrix {
  schema: string;
  family: string;
  language: string;
  job_key: string;
  counts: Record<MatrixState, number>;
  requirements: MatrixRow[];
}

export interface PlanDoc {
  schema: string;
  plan_sha256: string;
  plan_status: string;
  family: string;
  language: string;
  offer: { job_key: string; language: string; language_method: string };
  selected: {
    blocks: { id: string; bullets: string[]; reason: string }[];
    bullets: { id: string; reason?: string; covers?: string[]; gain?: number }[];
    skills: { id: string; reason?: string; covers?: string[]; gain?: number }[];
  };
  omitted: { type: string; id: string; reason: string; gain?: number | null }[];
  unsatisfied_required: { id: string; reasons: string[]; state: MatrixState; status: string }[];
  warnings: { code: string; [k: string]: unknown }[];
  limits: string[];
}

export interface ProvenanceInfo {
  status: "VERIFIED" | "UNVERIFIED";
  commit?: string;
  code?: string;
  reason?: string | null;
  path?: string | null;
  message?: string;
}

export interface PlanResult {
  ok: true;
  plan: PlanDoc;
  matrix: Matrix;
  texts: Record<string, string | null>;
  provenance: ProvenanceInfo;
  written: { file: string; sha256: string } | null;
}

export interface MatrixResult {
  ok: true;
  matrix: Matrix;
  texts: Record<string, string | null>;
  job: { title: string; company: string };
}

export interface PlansList {
  ok: true;
  plans: { file: string; valid: boolean; family?: string; language?: string; job_key?: string | null; plan_sha256?: string }[];
}

export interface RenderReport {
  ok: true;
  ready_to_send: false;
  review: "NOT_REVIEWED";
  template: string;
  paper: string;
  tex: { file: string; bytes: number; sha256: string };
  pdf: { status: "NOT_REQUESTED" | "COMPILED" | "UNAVAILABLE" | "FAILED"; file?: string; pages?: number; code?: string; message?: string; details?: Record<string, unknown> };
  layout: { page_target: number | null; pages: number | null; page_verdict: string };
  pending_directives: number;
  warnings: string[];
}

export interface AssembleResult {
  ok: true;
  assembly: { sections: unknown[]; skills: unknown; unsatisfied_required: unknown[]; warnings: { code: string }[] };
  outline: unknown;
}

export interface LatexStatus {
  ok: true;
  pdflatex: "FOUND" | "ABSENT";
  distribution: string | null;
  version: string | null;
}

export interface OutputsList {
  ok: true;
  files: { file: string; bytes: number; kind: "tex" | "pdf" }[];
}

// ---- packages, exact PDF, review (desktop/adapter/mcv_packages.py) ----------------------------
// The verdict strings come from the engine (`package.status`); nothing in the front end computes them.
export type Verdict = "READY_TO_SEND" | "NEEDS_REVIEW" | "BLOCKED";

export interface PackageState {
  status: string;
  reasons: string[];
}

export interface PackageRow {
  name: string;
  readable: boolean;
  code?: string;
  job_key?: string;
  language?: string;
  family?: string;
  document?: { available: boolean; sha256: string | null; pages: number | null; origin: string | null };
  state: PackageState | null;
}

export interface PackagesList {
  ok: true;
  total: number;
  truncated: boolean;
  packages: PackageRow[];
}

export interface StatusDetail {
  reason?: string;
  code: string;
  message: string;
}

export interface ReviewSummary {
  package: string;
  tailored_cv_id: string;
  job_key: string;
  language: string;
  family: string;
  document: {
    role: string;
    path: string | null;
    sha256: string | null;
    bytes: number | null;
    pages: number | null;
    origin: string | null;
    page_target: number | null;
    page_verdict: string;
  };
  reviewed: Record<string, string>;
  to_acknowledge: { unsatisfied_required: string[]; pending_directives: string[]; warnings: string[]; page_verdict: string };
  state_now: PackageState;
  limits: string[];
  approval_file: string;
  metadata: string;
}

export interface PackageReview {
  ok: true;
  summary: ReviewSummary;
  status: { status: string; reasons: string[]; warnings: string[]; details: StatusDetail[] };
  context: string;
  approval: { graphical: boolean; cli_available: boolean };
}

export interface PackageCreated {
  ok: true;
  ready_to_send: false;
  package: { name: string; state: string; reasons: string[]; pdf_origin: string | null; pdf_sha256: string | null; source_commit: string };
  next: string;
}

export interface PdfRead {
  ok: true;
  file: string;
  bytes: number;
  pages: number;
  sha256: string;
  base64?: string;
}

export interface ApprovalDone {
  ok: true;
  decision: "APPROVED" | "REJECTED";
  recorded: true;
  approval_file: string;
  document_sha256: string;
  status: { status: string; reasons: string[]; warnings: string[]; details: StatusDetail[] };
}

export interface Diagnostics {
  ok: true;
  mode: "embedded" | "development";
  engine: { status: string; version: string; python: string; embedded: boolean };
  git: { status: "FOUND" | "ABSENT"; version: string | null };
  provenance: { status: "VERIFIED" | "UNVERIFIABLE" | "NOT_CHECKED"; code: string | null; reason: string | null };
  latex: { pdflatex: "FOUND" | "ABSENT"; distribution: string | null; version: string | null; compile: "AVAILABLE" | "UNAVAILABLE" };
  offline: true;
}
