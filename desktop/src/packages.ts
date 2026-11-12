// Pure helpers for packages, history and review. No verdict is computed here: the verdict is whatever the engine returned.
import type { Verdict } from "./types";

export const SELECTED_PACKAGE_KEY = "mcv.review.package";

/** Presentation only: the colour family of a verdict the engine has already computed. Unknown values stay neutral. */
export function verdictTone(status: string | null | undefined): "success" | "warning" | "danger" | "neutral" {
  switch (status as Verdict) {
    case "READY_TO_SEND":
      return "success";
    case "NEEDS_REVIEW":
      return "warning";
    case "BLOCKED":
      return "danger";
    default:
      return "neutral";
  }
}

/** A suggestion for a package name: lowercase letters, digits, `.` and `-`. The engine has the last word. */
export function suggestPackageName(jobKey: string, family: string, language: string): string {
  const clean = (v: string) =>
    v
      .toLowerCase()
      .replace(/[^a-z0-9.-]+/g, "-")
      .replace(/-{2,}/g, "-")
      .replace(/^[-.]+|[-.]+$/g, "");
  const joined = [jobKey, family, language].map(clean).filter(Boolean).join("-");
  return joined.slice(0, 80).replace(/[-.]+$/g, "");
}

/** Hint only (the engine validates): lowercase letters, digits, `.` and `-`. */
export function looksLikePackageName(name: string): boolean {
  return /^[a-z0-9][a-z0-9.-]{0,79}$/.test(name);
}

/** The 12 characters a person types to confirm the PDF at the terminal (see `package approve`). */
export function confirmationPrefix(sha256: string | null | undefined): string {
  return sha256 ? sha256.slice(0, 12) : "";
}

export function shortHash(sha256: string | null | undefined): string {
  return sha256 ? sha256.slice(0, 12) + "…" + sha256.slice(-6) : "—";
}

/** Quote a value for a PowerShell double-quoted argument (the workspace path may hold spaces). */
function ps(value: string): string {
  return '"' + value.replace(/`/g, "``").replace(/"/g, '`"').replace(/\$/g, "`$") + '"';
}

/**
 * The existing interactive approval command. It is only shown: the application does not run it, and it still needs
 * an interactive terminal and the typed hash prefix.
 */
export function approveCommand(workspace: string, name: string): string {
  return `python -m modularcv package approve --name ${name} --root ${ps(workspace)} --reviewer "Your Name"`;
}

export function reviewCommand(workspace: string, name: string): string {
  return `python -m modularcv package review --name ${name} --root ${ps(workspace)}`;
}

export function statusCommand(workspace: string, name: string): string {
  return `python -m modularcv package status --name ${name} --root ${ps(workspace)}`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

/** Look a code up in a dictionary; unknown codes are kept visible, never hidden. */
export function explain(dict: Record<string, string>, code: string, fallback: string): string {
  if (dict[code]) return dict[code];
  const prefix = Object.keys(dict).find((k) => k.endsWith("*") && code.startsWith(k.slice(0, -1)));
  return prefix ? dict[prefix] : fallback;
}

/** SHA-256 of bytes, hex. Used to show that the bytes on screen are the bytes the engine hashed. */
export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as unknown as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function base64ToBytes(b64: string): Uint8Array {
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/** Clamp a zoom factor to the supported range. */
export function clampZoom(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(3, Math.max(0.5, Math.round(value * 100) / 100));
}

export function clampPage(page: number, pages: number): number {
  if (!Number.isFinite(page) || pages < 1) return 1;
  return Math.min(pages, Math.max(1, Math.trunc(page)));
}
