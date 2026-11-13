#!/usr/bin/env python3
"""Generate desktop/THIRD_PARTY_LICENSES.txt, the offline licence-text bundle shipped with ModularCV Desktop.

What it does
  * Reads the verbatim third-party texts kept in desktop/licenses/texts/ (each one taken from the official source named below).
  * Walks the Rust crates actually compiled into desktop.exe for the Windows target (`cargo tree -e normal`) and copies the
    licence, notice and copyright files shipped inside each published crate package (cargo registry sources).
  * Writes one deterministic text file. Identical texts are printed once, with the list of crates that use them.

Usage (from anywhere, Python 3.10+, standard library only; needs `cargo` and network access for `cargo fetch`):
    python desktop/tools/build_third_party_licenses.py            # write desktop/THIRD_PARTY_LICENSES.txt
    python desktop/tools/build_third_party_licenses.py --check    # fail if the committed file is out of date

The output does not depend on the machine: no absolute path, user name or timestamp is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
TEXTS = DESKTOP / "licenses" / "texts"
TAURI = DESKTOP / "src-tauri"
OUT = DESKTOP / "THIRD_PARTY_LICENSES.txt"
TARGET = "x86_64-pc-windows-msvc"
RULE = "=" * 78
THIN = "-" * 78

# Licence elections for "A OR B" expressions: the first alternative found in this list is the one relied on. Every licence
# file shipped in the crate package is reproduced anyway, whichever was elected.
PREFERENCE = ["MIT", "Zlib", "BSD-3-Clause", "BSD-2-Clause", "0BSD", "MIT-0", "Unlicense", "CC0-1.0", "Apache-2.0", "MPL-2.0", "Unicode-3.0"]

# Crates whose published package carries no licence file. The text below is the upstream file at the commit recorded in the
# package's own `.cargo_vcs_info.json`, or, for MPL-2.0, the canonical text shipped in sibling crates of the same project.
CRATE_FALLBACK = {
    "alloc-stdlib": ("crate-alloc-stdlib-LICENSE.txt",
                     "https://github.com/dropbox/rust-alloc-no-stdlib/blob/0a81fd6928ea3b33c8cd484aa4575d50ffb98012/LICENSE"),
    "webview2-com": ("crate-webview2-com-LICENSE.txt",
                     "https://github.com/wravery/webview2-rs/blob/edc2caf886175ccaebe86078c9cfe1ae2a187328/LICENSE"),
    "webview2-com-sys": ("crate-webview2-com-LICENSE.txt",
                         "https://github.com/wravery/webview2-rs/blob/edc2caf886175ccaebe86078c9cfe1ae2a187328/LICENSE"),
    "webview2-com-macros": ("crate-webview2-com-LICENSE.txt",
                            "https://github.com/wravery/webview2-rs/blob/dffa41a8a46d3f5565eefbff2de57d38d399f158/LICENSE"),
}
MPL_FALLBACK_SOURCE = "cssparser"  # selectors has no licence file; the MPL-2.0 text of its sibling crate (same Servo project) is used

LICENCE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|UNLICENSE|NOTICE|COPYRIGHT)", re.I)

# --------------------------------------------------------------------------------------------------------------------
# Components that are not Rust crates. Each entry: id, title, version, where it ships, licence, notes, [(text file, source)].
# --------------------------------------------------------------------------------------------------------------------
PY = "https://github.com/python/cpython/blob/v3.14.10/"
COMPONENTS = [
    dict(id="python", title="Python runtime (CPython)", version="3.14.10",
         where="engine sidecar: python314.dll, the .pyd extension modules, base_library.zip and the embedded standard-library modules",
         licence="PSF-2.0 (plus the historical licences of the Python lineage, all in the file below)",
         notes="The whole LICENSE file of the release is reproduced. The incorporated-software notices that apply to the shipped build "
               "follow in the next block.",
         texts=[("python-LICENSE.txt", PY + "LICENSE")]),
    dict(id="python-incorporated", title="Software incorporated in CPython 3.14.10 (notices of the official documentation)", version="3.14.10",
         where="python314.dll and the standard-library modules in the engine sidecar",
         licence="as stated in each section",
         notes="Sections of 'Licenses and Acknowledgements for Incorporated Software' (Doc/license.rst of the same release), reproduced "
               "unchanged as reStructuredText. Left out because they do not apply to the shipped build: OpenSSL (the shipped OpenSSL is 3.5.9, "
               "Apache-2.0, reproduced separately), expat, libffi, libmpdec (replaced by mpdecimal 4.0.0, below), the W3C C14N test suite, "
               "test_epoll, and the kqueue notice (not built on Windows). The Zero-Clause BSD licence of the documentation is not shipped.",
         rst_sections=["Mersenne Twister", "Sockets", "Asynchronous socket services", "Cookie management", "Execution tracing",
                       "UUencode and UUdecode functions", "XML Remote Procedure Calls", "SipHash24", "strtod and dtoa", "zlib",
                       "cfuhash", "mimalloc", "asyncio", "Global Unbounded Sequences (GUS)", "Zstandard bindings", "Unicode Character Database"],
         texts=[("python-license.rst", PY + "Doc/license.rst")]),
    dict(id="openssl", title="OpenSSL", version="3.5.9",
         where="engine sidecar: libcrypto-3.dll, libssl-3.dll (read from the DLL version resources)",
         licence="Apache-2.0",
         notes="Copyright line of the DLL version resource: 'Copyright 1998-2026 The OpenSSL Authors. All rights reserved.' "
               "The tag has no NOTICE file.",
         texts=[("openssl-LICENSE.txt", "https://github.com/openssl/openssl/blob/openssl-3.5.9/LICENSE.txt")]),
    dict(id="hacl", title="HACL* (verified cryptographic primitives vendored in CPython)", version="commit 8ba599b2f6c9701b3dc961db895b0856a2210f76",
         where="python314.dll (hash modules); version pinned by Misc/sbom.spdx.json of CPython 3.14.10",
         licence="Apache-2.0",
         notes="",
         texts=[("hacl-star-LICENSE.txt", "https://github.com/hacl-star/hacl-star/blob/8ba599b2f6c9701b3dc961db895b0856a2210f76/LICENSE")]),
    dict(id="bzip2", title="bzip2 / libbzip2", version="1.0.8",
         where="engine sidecar: _bz2.pyd (version of the bundled library as set by the CPython 3.14.10 Windows build, PCbuild/get_externals.bat)",
         licence="bzip2-and-libbzip2-1.0.6 (BSD-style)",
         notes="",
         texts=[("bzip2-LICENSE.txt", "https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE;hb=refs/tags/bzip2-1.0.8")]),
    dict(id="mpdecimal", title="mpdecimal (libmpdec)", version="4.0.0",
         where="engine sidecar: _decimal.pyd (version string found in the binary)",
         licence="BSD-2-Clause",
         notes="",
         texts=[("mpdecimal-COPYRIGHT.txt", "https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.0.tar.gz (file mpdecimal-4.0.0/COPYRIGHT.txt)")]),
    dict(id="xz", title="XZ Utils / liblzma", version="5.2.5",
         where="engine sidecar: _lzma.pyd (version as set by PCbuild/get_externals.bat of CPython 3.14.10; not readable from the binary)",
         licence="liblzma is in the public domain (no licence text is required; the statement of the authors is reproduced)",
         notes="",
         texts=[("xz-COPYING.txt", "https://github.com/tukaani-project/xz/blob/v5.2.5/COPYING")]),
    dict(id="zstd", title="Zstandard (zstd)", version="1.5.7",
         where="engine sidecar: _zstd.pyd (version string found in the binary)",
         licence="BSD-3-Clause OR GPL-2.0-only; the BSD-3-Clause terms are the ones relied on",
         notes="The GPL-2.0 alternative is not used and its text is not reproduced.",
         texts=[("zstd-LICENSE.txt", "https://github.com/facebook/zstd/blob/v1.5.7/LICENSE")]),
    dict(id="zlib-ng", title="zlib-ng (zlib compatibility mode)", version="2.2.4 (reports itself as 1.3.1.zlib-ng)",
         where="engine sidecar: python314.dll (string found in the binary). The same zlib licence also covers the copy of zlib that PyInstaller's "
               "bootloader embeds in mcv-engine.exe (version not determined).",
         licence="Zlib",
         notes="",
         texts=[("zlib-ng-LICENSE.md", "https://github.com/zlib-ng/zlib-ng/blob/2.2.4/LICENSE.md")]),
    dict(id="pyinstaller", title="PyInstaller (bootloader, loader modules, run-time hooks)", version="6.22.3",
         where="engine sidecar: the bootloader that is mcv-engine.exe, the loader modules and the run-time hooks embedded in it",
         licence="bootloader and loader modules: GPL-2.0-or-later WITH the PyInstaller Bootloader Exception; run-time hooks and fake modules: Apache-2.0",
         notes="Copyright (c) 2010-2023 PyInstaller Development Team; Copyright (c) 2005-2009 Giovanni Bajo; based on earlier work "
               "(c) 2002 McMillan Enterprises, Inc. (COPYING.txt of v6.22.3). The Bootloader Exception gives unlimited permission to link or "
               "embed the compiled bootloader and related files into combinations with other programs and to distribute them without "
               "restriction from those files, so the GPL text is not reproduced for the bootloader and the loader modules. The run-time hooks "
               "embedded in the executable are Apache-2.0, whose text is reproduced below under 'Apache License 2.0 (generic)'. "
               "The program is not modified by ModularCV: only unmodified PyInstaller files are embedded. Source: "
               "https://github.com/pyinstaller/pyinstaller/tree/v6.22.3 .",
         texts=[]),
    dict(id="webview2-loader", title="Microsoft WebView2 SDK, static loader (WebView2LoaderStatic.lib)", version="1.0.3800.47",
         where="desktop.exe: linked statically by the webview2-com-sys crate (CreateWebViewEnvironmentWithOptionsInternal is present in the binary)",
         licence="BSD-3-Clause style licence of the Microsoft.Web.WebView2 NuGet package",
         notes="Version established by comparison: the x64 WebView2LoaderStatic.lib inside webview2-com-sys 0.39.1 is byte-identical to "
               "build/native/x64/WebView2LoaderStatic.lib of the Microsoft.Web.WebView2 1.0.3800.47 package (no other stable release from 1.0.3000 "
               "to 1.0.4129 matches). The text below is that package's LICENSE.txt (identical in 1.0.3650.58). The package NOTICE.txt only lists "
               "ANTLR 3.5.2 and StringTemplate 4.0.9 (BSD-3-Clause), used by other parts of the SDK; neither name appears in the loader library "
               "or in desktop.exe, so that notice is not reproduced. The WebView2 Runtime itself is not shipped.",
         texts=[("webview2-sdk-LICENSE.txt", "https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3800.47 (file LICENSE.txt)")]),
    dict(id="nsis", title="NSIS (Nullsoft Scriptable Install System), installer stub and uninstaller stub", version="3.13",
         where="ModularCV Desktop_0.5.0-beta.1_x64-setup.exe and the installed uninstall.exe: the 'lzma_solid' unicode stub, the compression "
               "module (LZMA, solid) and the System, nsDialogs, NSISdl and UserInfo plug-ins",
         licence="zlib/libpng for the stub, plug-ins and headers; Common Public License 1.0 with the NSIS special exception for the LZMA compression "
                 "module; the bzip2 module is not used",
         notes="Copyright (C) 1999-2026 Contributors (COPYING of NSIS 3.13, the distribution pinned by the Tauri CLI: "
               "https://github.com/tauri-apps/binary-releases/releases/tag/nsis-3.13). The installer compresses with LZMA (SetCompressor /SOLID lzma), so the "
               "CPL-1.0 text of the LZMA module is reproduced in the file below. ModularCV did not modify NSIS. Source code of NSIS is available at "
               "https://nsis.sourceforge.io/ (mirror: https://github.com/kichik/nsis); the LZMA module's source is part of that tree. The "
               "provisions of the CPL-1.0 that differ from the MIT licence of ModularCV apply only to the LZMA module and are offered by its "
               "contributors alone, not by ModularCV; ModularCV gives no warranty.",
         texts=[("nsis-3.13-COPYING.txt", "COPYING of the NSIS 3.13 distribution (tauri-apps/binary-releases, nsis-3.13.zip)")]),
    dict(id="nsis-tauri-utils", title="nsis_tauri_utils (NSIS plug-in used by Tauri's installer template)", version="0.5.3",
         where="setup.exe (SemverCompare, RunAsUser and related calls)",
         licence="MIT OR Apache-2.0 (MIT relied on; both texts reproduced)",
         notes="Copyright (c) 2019 - 2022 Tauri Programme within The Commons Conservancy. The plug-in DLL (SHA-1 75197FEE3C6A814FE035788D1C34EAD39349B860) is "
               "the one pinned by the Tauri CLI. The Rust crates compiled into that DLL were not itemised.",
         texts=[("nsis-tauri-utils-LICENSE_MIT.txt", "https://github.com/tauri-apps/nsis-tauri-utils/blob/nsis_tauri_utils-v0.5.3/LICENSE_MIT"),
                ("nsis-tauri-utils-LICENSE_APACHE-2.0.txt", "https://github.com/tauri-apps/nsis-tauri-utils/blob/nsis_tauri_utils-v0.5.3/LICENSE_APACHE-2.0")]),
    dict(id="rust-std", title="Rust standard library and compiler runtime (statically linked into desktop.exe)", version="rustc 1.99.1 (58cf8f9c3, 2026-10-13)",
         where="desktop.exe: core, alloc, std, compiler-builtins and the other crates of the standard library",
         licence="MIT OR Apache-2.0 (the MIT terms are the ones relied on; both texts are reproduced)",
         notes="Copyright (c) The Rust Project Contributors. The COPYRIGHT file of the same commit lists the third-party code kept in the "
               "Rust tree and is reproduced in full.",
         texts=[("rust-LICENSE-MIT.txt", "https://github.com/rust-lang/rust/blob/58cf8f9c35b355199727627d07ae34a4e2846d67/LICENSE-MIT"),
                ("rust-LICENSE-APACHE.txt", "https://github.com/rust-lang/rust/blob/58cf8f9c35b355199727627d07ae34a4e2846d67/LICENSE-APACHE"),
                ("rust-COPYRIGHT.txt", "https://github.com/rust-lang/rust/blob/58cf8f9c35b355199727627d07ae34a4e2846d67/COPYRIGHT")]),
    dict(id="react", title="React", version="19.3.1", where="front end bundle (dist/assets, embedded in desktop.exe)", licence="MIT",
         notes="", texts=[("npm-react-LICENSE.txt", "https://registry.npmjs.org/react/-/react-19.3.1.tgz (file package/LICENSE)")]),
    dict(id="react-dom", title="React DOM", version="19.3.1", where="front end bundle", licence="MIT",
         notes="", texts=[("npm-react-dom-LICENSE.txt", "https://registry.npmjs.org/react-dom/-/react-dom-19.3.1.tgz (file package/LICENSE)")]),
    dict(id="scheduler", title="scheduler", version="0.28.0", where="front end bundle", licence="MIT",
         notes="", texts=[("npm-scheduler-LICENSE.txt", "https://registry.npmjs.org/scheduler/-/scheduler-0.28.0.tgz (file package/LICENSE)")]),
    dict(id="tauri-api", title="@tauri-apps/api", version="2.12.4", where="front end bundle", licence="Apache-2.0 OR MIT (MIT relied on; both texts reproduced)",
         notes="Copyright (c) 2017 - Present Tauri Apps Contributors.",
         texts=[("npm-tauri-api-LICENSE-MIT.txt", "https://registry.npmjs.org/@tauri-apps/api/-/api-2.12.4.tgz (file package/LICENSE-MIT)"),
                ("npm-tauri-api-LICENSE-APACHE-2.0.txt", "https://registry.npmjs.org/@tauri-apps/api/-/api-2.12.4.tgz (file package/LICENSE-APACHE-2.0)")]),
    dict(id="tauri-plugin-dialog-js", title="@tauri-apps/plugin-dialog", version="2.8.4", where="front end bundle", licence="MIT OR Apache-2.0 (MIT relied on; both texts reproduced)",
         notes="The npm package ships only an SPDX file; the texts are those of the plugin repository at the matching tag.",
         texts=[("npm-tauri-plugin-dialog-LICENSE_MIT.txt", "https://github.com/tauri-apps/plugins-workspace/blob/dialog-v2.8.4/LICENSE_MIT"),
                ("npm-tauri-plugin-dialog-LICENSE_APACHE-2.0.txt", "https://github.com/tauri-apps/plugins-workspace/blob/dialog-v2.8.4/LICENSE_APACHE-2.0")]),
    dict(id="pdfjs", title="pdf.js (pdfjs-dist)", version="6.5.438", where="front end bundle: PdfViewer chunk and pdf.worker.min-*.mjs", licence="Apache-2.0",
         notes="The worker file keeps the notice of the Mozilla Foundation (first block below). The package ships no NOTICE file. "
               "No pdf.js fonts, CMaps or WASM files are shipped.",
         texts=[("npm-pdfjs-dist-worker-header.txt", "header comment of dist/assets/pdf.worker.min-*.mjs, as produced by the build"),
                ("npm-pdfjs-dist-LICENSE.txt", "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz (file package/LICENSE)")]),
]

UNRESOLVED = """\
Microsoft Visual C++ runtime, Universal C Runtime (UCRT) and the statically linked C runtime
  What ships: (1) engine sidecar: VCRUNTIME140.dll 14.51.36247.0, a Microsoft-signed file that is byte-identical to the copy installed with the
  python.org Python 3.14.10 on the build computer (it is not the copy of Visual Studio's own redistributable folder, which is 14.44.35211.0);
  ucrtbase.dll 10.0.22621.3233 and the api-ms-win-*.dll forwarders (Microsoft-signed, version 10.0.22621.3233, origin on the build computer not
  established). (2) desktop.exe imports the UCRT through api-ms-win-crt-*.dll of Windows (not shipped) and links the MSVC C runtime statically.
  Official position (Microsoft, 'Redistribute Visual C++ files' and 'Universal CRT deployment'): redistributing individual Visual C++ runtime
  binaries is limited to licensed Visual Studio users and subject to the Microsoft Software License Terms; for Visual Studio 2022 Community,
  Professional and Enterprise the REDIST list allows copying the unmodified files under the VC redist folder with a program. The UCRT is an
  operating-system component on Windows 10 and later, the system copy is always used there, and local copies are ignored.
  Not established: that the python.org copy of VCRUNTIME140.dll and the UCRT files of unknown origin were obtained under a redistribution grant
  that covers this installer; that statically linking the MSVC runtime into desktop.exe needs no further notice. These Microsoft licence texts are
  not reproduced and no Microsoft text is available offline in this installer. Open compliance item.

WebView2 SDK loader
  Version and licence text are established (see its entry). The loader is Microsoft code under the BSD-style licence reproduced above.

NSIS installer
  NSIS 3.13, its LZMA-solid stub, the plug-ins used and nsis_tauri_utils 0.5.3 are identified and their licence texts are reproduced above. Whether
  the CPL-1.0 requirement to state where the LZMA module's source is available is met by the statement in the NSIS entry is a reading of the
  licence, not a legal opinion.

Unicode data in unicodedata.pyd
  The Unicode Character Database notice of CPython is reproduced above ('Unicode Character Database' section). The exact UCD version
  embedded was not independently verified.

Bundled build tooling
  Crates that run only at build time (tauri-build, cc, embed-resource, winres and similar) are not redistributed and are not covered.

Compliance statement
  This bundle reproduces the licence texts and notices of the components that could be identified as redistributed. It is the result of a
  best-effort audit, not legal advice, and it does not claim that every obligation of every component is met.
"""


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


SCAN_MARKER = "privacy-scan: ignore-file"


def read_text(path: Path) -> str:
    """The verbatim text of a file (LF newlines). A leading privacy-scan marker line, added only to files that hold
    third-party e-mail addresses, is not part of the text and is dropped."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")  # fails loudly on an unexpected encoding rather than guessing
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith(SCAN_MARKER):
        text = text.split("\n\n", 1)[1]
    return text.strip("\n") + "\n"


def rst_section(rst: str, title: str) -> str:
    lines = rst.split("\n")
    for i in range(len(lines) - 1):
        if lines[i].strip() == title and lines[i + 1].strip() and set(lines[i + 1].strip()) <= set("-=^~\"'`#*+"):
            j = i + 2
            while j < len(lines) - 1:
                if lines[j].strip() and lines[j + 1].strip() and set(lines[j + 1].strip()) <= set("-=^~\"'`#*+") \
                        and len(lines[j + 1].strip()) >= len(lines[j].strip()) - 1 and lines[j][0] not in " \t":
                    break
                j += 1
            else:
                j = len(lines)
            block = "\n".join(lines[i:j]).rstrip("\n")
            # drop a trailing `.. _label:` line that belongs to the next section
            block = re.sub(r"\n\.\. _[\w-]+:\s*$", "", block).rstrip("\n")
            return block + "\n"
    raise SystemExit("section not found in python-license.rst: " + title)


def run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True).stdout.decode("utf-8", "replace")


def spdx_leaves(expr: str) -> list[str]:
    return [t for t in re.split(r"[\s()/]+|\bAND\b|\bOR\b|\bWITH\b", expr) if t]


def election(expr: str) -> str:
    e = re.sub(r"\s*/\s*", " OR ", expr.strip())
    # AND binds the parenthesised group; this project's expressions never nest deeper than one level.
    def pick(alts: list[str]) -> str:
        for p in PREFERENCE:
            if p in alts:
                return p
        return alts[0]
    def solve(s: str) -> list[str]:
        s = s.strip()
        parts, depth, cur = [], 0, ""
        for tok in re.split(r"(\(|\)|\s+)", s):
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
            if depth == 0 and tok.strip() == "AND":
                parts.append(cur); cur = ""
            else:
                cur += tok
        parts.append(cur)
        if len(parts) > 1:
            out = []
            for p in parts:
                out += solve(p)
            return out
        s = parts[0].strip()
        if s.startswith("(") and s.endswith(")") and s.count("(") == 1:
            return solve(s[1:-1])
        alts = [a.strip() for a in re.split(r"\s+OR\s+", s)]
        return [pick(alts)]
    return " AND ".join(solve(e))


def compiled_crates() -> dict[tuple[str, str], dict]:
    run(["cargo", "fetch", "--locked", "--target", TARGET], TAURI)
    tree = run(["cargo", "tree", "--locked", "--target", TARGET, "-e", "normal", "--prefix", "none", "--format", "{p}"], TAURI)
    wanted = set()
    for line in tree.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+) v(\S+)", line.strip())
        if m and m.group(1) != "desktop":
            wanted.add((m.group(1), m.group(2)))
    meta = json.loads(run(["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform", TARGET], TAURI))
    pk = {(p["name"], p["version"]): p for p in meta["packages"]}
    missing = wanted - set(pk)
    if missing:
        raise SystemExit(f"crates absent from cargo metadata: {sorted(missing)}")
    return {k: pk[k] for k in sorted(wanted)}


def crate_texts(crates: dict) -> tuple[dict[str, dict], list[tuple]]:
    """Return {sha: {text, names:[crate...], files:set}} and the list of crates that needed a fallback."""
    blocks: dict[str, dict] = {}
    fallbacks = []
    mpl_text = None
    for (name, ver), p in crates.items():
        pkg = Path(p["manifest_path"]).parent
        files = sorted(f.name for f in pkg.iterdir() if f.is_file() and LICENCE_FILE.match(f.name))
        entries = [(f, read_text(pkg / f)) for f in files]
        if not any(re.match(r"(LICEN|COPYING|UNLICENSE)", f, re.I) for f, _ in entries):
            if name in CRATE_FALLBACK:
                fn, src = CRATE_FALLBACK[name]
                entries.append((f"(upstream {fn})", read_text(TEXTS / fn)))
                fallbacks.append((name, ver, src))
            elif p["license"] == "MPL-2.0":
                if mpl_text is None:
                    sib = next(q for (n, _), q in crates.items() if n == MPL_FALLBACK_SOURCE)
                    d = Path(sib["manifest_path"]).parent
                    mpl_text = read_text(next(d / f for f in os.listdir(d) if re.match(r"LICENSE", f)))
                entries.append(("(MPL-2.0 text of the cssparser package)", mpl_text))
                fallbacks.append((name, ver, "MPL-2.0 canonical text from the cssparser package; the source files carry the MPL-2.0 header"))
            else:
                raise SystemExit(f"no licence text for {name} {ver}")
        for fname, text in entries:
            h = sha(text.encode("utf-8"))
            b = blocks.setdefault(h, dict(text=text, names=[], files=set()))
            b["names"].append(f"{name} {ver}")
            b["files"].add(re.sub(r"^\(.*\)$", "fallback", fname))
    return blocks, fallbacks


def build() -> str:
    crates = compiled_crates()
    blocks, fallbacks = crate_texts(crates)
    out: list[str] = []
    w = out.append

    w("ModularCV Desktop 0.5.0-beta.1: third-party licence texts and notices")
    w(SCAN_MARKER + " (verbatim third-party notices keep their rights holders' own addresses; a test allows only those)")
    w(RULE)
    w("This file ships with the application (next to LICENSE and THIRD_PARTY_NOTICES.md in the `legal` folder of the install folder).")
    w("It reproduces the licence texts and copyright notices of the third-party components that are redistributed with the application.")
    w("")
    w("- LICENSE                       : the ModularCV project licence (MIT), kept separate and unchanged.")
    w("- THIRD_PARTY_NOTICES.md        : the inventory (names, versions, licences, sources).")
    w("- THIRD_PARTY_LICENSES.txt      : this file, the texts themselves.")
    w("")
    w("Texts are copied unchanged from the official sources named next to each one (the SHA-256 of each text, with LF newlines, is given).")
    w("Where a component is offered under several licences, the terms relied on are stated; every licence file shipped in the component's")
    w("own package is still reproduced. Nothing here modifies a right holder's name or terms.")
    w("This file is generated by desktop/tools/build_third_party_licenses.py. It is the result of a best-effort audit, not legal advice.")
    w("")
    w("CONTENTS")
    w("  Part 1. Components that are not Rust crates (Python runtime and native libraries, PyInstaller, Rust standard library, JavaScript)")
    w("  Part 2. Rust crates compiled into desktop.exe (licence election, then the texts)")
    w("  Part 3. MPL-2.0 components: how to obtain the source code")
    w("  Part 4. Apache License 2.0 (generic)")
    w("  Part 5. Unresolved items")
    w("")

    # ---- Part 1
    w(RULE); w("PART 1. COMPONENTS THAT ARE NOT RUST CRATES"); w(RULE); w("")
    rst_all = None
    for c in COMPONENTS:
        w(RULE)
        w(f"{c['title']}  {c['version']}")
        w(THIN)
        w(f"Where           : {c['where']}")
        w(f"Licence         : {c['licence']}")
        if c["notes"]:
            w("Notes           : " + c["notes"])
        for fn, src in c["texts"]:
            w(f"Source of text  : {src}")
            w(f"SHA-256 of text : {sha(read_text(TEXTS / fn).encode('utf-8'))} ({fn}, LF newlines)")
        w(THIN); w("")
        if "rst_sections" in c:
            rst_all = read_text(TEXTS / "python-license.rst")
            for t in c["rst_sections"]:
                w(rst_section(rst_all, t).rstrip("\n")); w("")
        else:
            for fn, _ in c["texts"]:
                w(read_text(TEXTS / fn).rstrip("\n")); w("")
    # ---- Part 2
    w(RULE); w("PART 2. RUST CRATES COMPILED INTO desktop.exe (Windows target)"); w(RULE); w("")
    w(f"{len(crates)} crates are compiled in (cargo tree -e normal --target {TARGET}); the list with versions and sources is in")
    w("THIRD_PARTY_NOTICES.md. Each distinct licence file of those crates is printed once, with the crates that use it.")
    w("")
    w("Licence election for crates offered under several licences ('A OR B'): the terms relied on are chosen in this order:")
    w("  " + ", ".join(PREFERENCE) + ". Expressions joined by AND all apply.")
    w("")
    by_expr: dict[str, list[str]] = {}
    for (n, v), p in crates.items():
        by_expr.setdefault(p["license"], []).append(f"{n} {v}")
    w("Expression found in the crate metadata -> terms relied on (number of crates)")
    for expr in sorted(by_expr):
        w(f"  {expr} -> {election(expr)} ({len(by_expr[expr])})")
    w("")
    if fallbacks:
        w("Crates whose published package carries no licence file (text taken from the upstream source named):")
        for n, v, s in fallbacks:
            w(f"  {n} {v}: {s}")
        w("")
    ordered = sorted(blocks.values(), key=lambda b: (b["names"][0].lower(), sha(b["text"].encode())))
    for i, b in enumerate(ordered, 1):
        w(THIN)
        w(f"[{i:03d}] Used by : " + ", ".join(sorted(set(b["names"]))))
        w(f"       File(s)  : " + ", ".join(sorted(b["files"])))
        w(THIN)
        w(b["text"].rstrip("\n")); w("")
    # ---- Part 3
    w(RULE); w("PART 3. MPL-2.0 COMPONENTS: SOURCE CODE"); w(RULE); w("")
    mpl = [(n, v, p) for (n, v), p in crates.items() if "MPL-2.0" in p["license"]]
    w("The following crates are licensed under the Mozilla Public License 2.0 and are compiled, unmodified, into desktop.exe.")
    w("Under MPL-2.0 section 3.2 the Source Code Form of this Covered Software remains available to you under the terms of the MPL-2.0;")
    w("its text is reproduced in Part 2 (see the entries that list these crates). It is available at the addresses below, for the exact")
    w("versions that are compiled in:")
    w("")
    for n, v, p in mpl:
        w(f"  {n} {v}")
        w(f"    package (source) : https://static.crates.io/crates/{n}/{n}-{v}.crate  (browse: https://crates.io/crates/{n}/{v})")
        w(f"    repository       : {p.get('repository')}")
    w("")
    w("ModularCV did not modify these crates. The exact versions are pinned in desktop/src-tauri/Cargo.lock of the ModularCV source tree")
    w("(https://github.com/Felipe-Portugal/ModularCV), from which desktop.exe can be rebuilt with `cargo build --release --locked`.")
    w("Files of the MPL-2.0 packages stay under the MPL-2.0; the rest of ModularCV, which only links them, stays under the MIT licence.")
    w("")
    # ---- Part 4
    w(RULE); w("PART 4. APACHE LICENSE 2.0 (GENERIC)"); w(RULE); w("")
    w("Reference text for the Apache-2.0 components that name no specific copyright line of their own: the PyInstaller run-time hooks")
    w("(Copyright (c) PyInstaller Development Team) and generic references above. Official text, copied from the OpenSSL 3.5.9 tag.")
    w("")
    w(read_text(TEXTS / "openssl-LICENSE.txt").rstrip("\n")); w("")
    # ---- Part 5
    w(RULE); w("PART 5. UNRESOLVED ITEMS"); w(RULE); w("")
    w(UNRESOLVED)
    return "\n".join(out).replace("\r", "") + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed file differs from a fresh generation")
    args = ap.parse_args()
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("THIRD_PARTY_LICENSES.txt is out of date: rerun desktop/tools/build_third_party_licenses.py", file=sys.stderr)
            return 1
        print("THIRD_PARTY_LICENSES.txt is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name}: {len(text.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
