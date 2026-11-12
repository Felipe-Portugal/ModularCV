import { invoke } from "@tauri-apps/api/core";
import type { AdapterFailure, DemoKind, DemoWorkspace, Result, SaveOk, ValidationResult, WorkspaceState } from "./types";

/**
 * Thin Rust bridge. The front end can only request the allowed `facts_check`
 * operation; it never touches a shell or a process directly. A future packaged
 * sidecar only changes the Rust side.
 */
export const OPERATION_FACTS_CHECK = "facts_check" as const;

export function validateWorkspace(workspace: string): Promise<ValidationResult> {
  return invoke<ValidationResult>("validate_workspace", {
    operation: OPERATION_FACTS_CHECK,
    workspace,
  });
}

export function prepareDemoWorkspace(kind: DemoKind): Promise<DemoWorkspace> {
  return invoke<DemoWorkspace>("prepare_demo_workspace", { kind });
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

// ---- structured reads and writes (allowed Rust commands only) -------------------------------


async function guarded<T>(call: Promise<Result<T>>): Promise<Result<T>> {
  try {
    return await call;
  } catch (e) {
    const failure: AdapterFailure = { ok: false, code: "BRIDGE_ERROR", message: String(e), details: [] };
    return failure;
  }
}

export function readWorkspace(workspace: string) {
  return guarded<WorkspaceState>(invoke("read_workspace", { workspace }));
}

export function saveFact(workspace: string, request: Record<string, unknown>) {
  return guarded<SaveOk>(invoke("save_fact", { workspace, request }));
}

export function saveProfile(workspace: string, request: Record<string, unknown>) {
  return guarded<SaveOk>(invoke("save_profile", { workspace, request }));
}

/** Native Windows folder picker. Returns null when the user cancels. */
export async function pickFolder(): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({ directory: true, multiple: false });
  return typeof picked === "string" ? picked : null;
}

/**
 * One allowed adapter operation. The Rust side refuses any name outside its closed list, so the front end
 * cannot ask for another command; there is no shell or process access from JavaScript.
 */
export function adapter<T>(workspace: string, operation: string, request: Record<string, unknown> = {}) {
  return guarded<T>(invoke("adapter_call", { workspace, operation, request }));
}

/** Native file dialog (read-only choice of a file to import). Returns null on cancel. */
export async function pickFile(extensions: string[]): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({ directory: false, multiple: false, filters: [{ name: "Offer", extensions }] });
  return typeof picked === "string" ? picked : null;
}

/** Show a generated file in Windows Explorer (workspace paths only). */
export function revealInExplorer(workspace: string, relative?: string): Promise<void> {
  return invoke<void>("reveal_in_explorer", { workspace, relative: relative ?? null });
}

/** Open a package or generated PDF in the system's PDF reader. The Rust side validates it first (fixed workspace locations). */
export function openPdf(workspace: string, target: { package?: string; output?: string }): Promise<void> {
  return invoke<void>("open_pdf", { workspace, package: target.package ?? null, output: target.output ?? null });
}

/** Read-only environment diagnostics (embedded engine, Git, provenance, LaTeX). Works without a workspace. */
export function diagnostics(workspace?: string) {
  return guarded<import("./types").Diagnostics>(invoke("diagnostics", { workspace: workspace || null }));
}
