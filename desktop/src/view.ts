import type { Outcome, ValidationResult } from "./types";

export type Tone = "success" | "danger" | "warning";

/** Only `valid` is success; everything else is shown as a problem. */
export function toneOf(outcome: Outcome): Tone {
  if (outcome === "valid") return "success";
  if (outcome === "invalid" || outcome === "config_error") return "warning";
  return "danger";
}

/** Success needs a real engine verdict: outcome, exit code and report status must all agree. */
export function isSuccess(result: ValidationResult | null): boolean {
  return !!result && result.outcome === "valid" && result.exit_code === 0 && result.report?.status === "OK";
}

export function shortHash(hash: string | null): string {
  return hash ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : "—";
}
