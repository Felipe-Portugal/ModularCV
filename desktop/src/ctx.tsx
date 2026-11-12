import { createContext, useContext } from "react";
import type { Dict } from "./i18n";
import type { Strings } from "./strings";
import type { AdapterFailure, Lang, Page, Problem, WorkspaceState } from "./types";

export interface Ctx {
  t: Dict;
  m: Strings;
  lang: Lang;
  workspace: string;
  state: WorkspaceState | null;
  loading: boolean;
  loadError: AdapterFailure | null;
  reload: () => Promise<void>;
  navigate: (page: Page) => void;
  setDirty: (key: string, dirty: boolean) => void;
}

export const AppCtx = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("AppCtx missing");
  return ctx;
}

/** Human message for an adapter failure: friendly text first, engine detail kept. */
export function failureText(m: Strings, code: string, message: string): string {
  return m.errors[code] ?? m.jobErrors[code] ?? m.pkgErrors[code] ?? message;
}

export function pickText(map: Record<string, string> | undefined, lang: Lang): string {
  if (!map) return "";
  return map[lang] ?? Object.values(map)[0] ?? "";
}

export type { Problem };
