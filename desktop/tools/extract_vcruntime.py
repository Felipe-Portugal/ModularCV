#!/usr/bin/env python3
"""Extract the x64 vcruntime140.dll from Microsoft's Visual C++ Redistributable bundle (vc_redist.x64.exe), unmodified.

    python extract_vcruntime.py VC_REDIST_X64_EXE OUTPUT_DLL

The bundle carries Microsoft cabinet archives after its executable part. Each one is carved out by its `MSCF` header and unpacked with
Windows' own expand.exe; the file `vcruntime140.dll_amd64` is copied byte for byte. Nothing is installed and no administrator right is needed.
Prints the SHA-256 of the extracted file. Windows only, standard library only.
"""
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    data = open(argv[1], "rb").read()
    work = tempfile.mkdtemp(prefix="mcv-vcredist-")
    try:
        found = None
        starts = [m.start() for m in re.finditer(b"MSCF\x00\x00\x00\x00", data)]
        for n, pos in enumerate(starts):
            size = struct.unpack("<I", data[pos + 8:pos + 12])[0]
            cab = os.path.join(work, f"c{n}.cab")
            open(cab, "wb").write(data[pos:pos + size])
            out = os.path.join(work, f"c{n}")
            os.makedirs(out)
            subprocess.run(["expand", "-F:*", cab, out], capture_output=True, check=False)
            for inner in sorted(os.listdir(out)):
                p = os.path.join(out, inner)
                head = open(p, "rb").read(8)
                if head[:4] == b"MSCF":  # a cabinet inside the cabinet: unpack it too
                    sub = os.path.join(work, f"c{n}_{inner}")
                    os.makedirs(sub)
                    shutil.copyfile(p, sub + ".cab")
                    subprocess.run(["expand", "-F:*", sub + ".cab", sub], capture_output=True, check=False)
                    cand = os.path.join(sub, "vcruntime140.dll_amd64")
                    if os.path.isfile(cand):
                        found = cand
        if not found:
            print("vcruntime140.dll_amd64 not found in the bundle", file=sys.stderr)
            return 1
        shutil.copyfile(found, argv[2])
        print(hashlib.sha256(open(argv[2], "rb").read()).hexdigest().upper())
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
