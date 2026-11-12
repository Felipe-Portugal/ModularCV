import { describe, expect, it } from "vitest";
import { approveCommand, base64ToBytes, clampPage, clampZoom, confirmationPrefix, explain, formatBytes, looksLikePackageName, sha256Hex, shortHash, suggestPackageName, verdictTone } from "./packages";

describe("verdictTone", () => {
  it("only colours what the engine returned; unknown stays neutral", () => {
    expect(verdictTone("READY_TO_SEND")).toBe("success");
    expect(verdictTone("NEEDS_REVIEW")).toBe("warning");
    expect(verdictTone("BLOCKED")).toBe("danger");
    expect(verdictTone("whatever")).toBe("neutral");
    expect(verdictTone(null)).toBe("neutral");
  });
});

describe("package names", () => {
  it("suggests a lowercase engine-valid name", () => {
    expect(suggestPackageName("Example_Backend Intern", "software", "en")).toBe("example-backend-intern-software-en");
    expect(suggestPackageName("a..b", "x", "fr")).toBe("a..b-x-fr");
    expect(suggestPackageName("---", "", "")).toBe("");
    expect(looksLikePackageName(suggestPackageName("Offer (fictional)!", "software", "en"))).toBe(true);
  });
  it("rejects names the engine would refuse", () => {
    for (const bad of ["", "Bad Name", "../x", "a/b", "UPPER", "-lead"]) expect(looksLikePackageName(bad)).toBe(false);
  });
});

describe("approval guidance", () => {
  it("builds the existing interactive command, never a run", () => {
    const cmd = approveCommand("D:\\Fictional Folder\\ws", "demo-cv");
    expect(cmd).toContain("package approve --name demo-cv");
    expect(cmd).toContain('--root "D:\\Fictional Folder\\ws"');
    expect(cmd.startsWith("python -m modularcv ")).toBe(true);
  });
  it("quotes dangerous characters of a path", () => {
    expect(approveCommand('C:\\a"b$c', "x")).toContain('"C:\\a`"b`$c"');
  });
  it("prefix is the 12 characters the terminal asks for", () => {
    expect(confirmationPrefix("0123456789abcdef0123")).toBe("0123456789ab");
    expect(confirmationPrefix(null)).toBe("");
    expect(shortHash("0123456789abcdef0123456789abcdef")).toBe("0123456789ab…abcdef");
  });
});

describe("explain", () => {
  const dict = { A: "exact", "SNAPSHOT_*": "family" };
  it("prefers exact, then prefix, then the fallback", () => {
    expect(explain(dict, "A", "x")).toBe("exact");
    expect(explain(dict, "SNAPSHOT_MISSING", "x")).toBe("family");
    expect(explain(dict, "UNKNOWN", "fallback")).toBe("fallback");
  });
});

describe("viewer helpers", () => {
  it("clamps zoom and page", () => {
    expect(clampZoom(10)).toBe(3);
    expect(clampZoom(0.1)).toBe(0.5);
    expect(clampZoom(NaN)).toBe(1);
    expect(clampPage(0, 3)).toBe(1);
    expect(clampPage(9, 3)).toBe(3);
    expect(clampPage(2.7, 3)).toBe(2);
    expect(clampPage(1, 0)).toBe(1);
  });
  it("hashes exactly the bytes it is given", async () => {
    const bytes = base64ToBytes(btoa("abc"));
    expect(await sha256Hex(bytes)).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
  it("formats sizes", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(102893)).toBe("100.5 KB");
  });
});
