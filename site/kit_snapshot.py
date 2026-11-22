"""The kit's `tools/` and `samples/` at the commit the site is built from, published beside the site, so *My apps*
(developer.ivendnext.com/apps.html) makes and changes apps with the kit as it stands after every merge, with no person
moving a pin.

    python3 site/kit_snapshot.py site/_out            # writes _out/kit/<commit>.tar.gz and _out/kit/snapshot.json

The snapshot is every file of `tools/` and `samples/` except a sample's screenshots and any `__pycache__`, each with
time 0 and no owner, gzipped with time 0: the same bytes for the same commit on every run. `snapshot.json` names the
commit (twelve characters) and the file's SHA-256; My apps reads it, fetches the file, checks the SHA-256 and unpacks it.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile

KIT = pathlib.Path(__file__).resolve().parent.parent


def build(ref: str = "HEAD") -> tuple[str, bytes]:
    """(the commit's twelve characters, the snapshot's bytes)."""
    commit = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--short=12", ref], capture_output=True, text=True,
                            check=True).stdout.strip()
    raw = subprocess.run(["git", "-C", str(KIT), "archive", "--format=tar", commit, "tools", "samples"],
                         capture_output=True, check=True).stdout
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw)) as src, gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode="w") as dst:
        for m in src.getmembers():
            if not m.isfile() or "/screenshots/" in m.name or "/__pycache__/" in m.name:
                continue
            m.mtime, m.uid, m.gid, m.uname, m.gname = 0, 0, 0, "", ""
            dst.addfile(m, src.extractfile(m))
    return commit, out.getvalue()


def write(out_dir: pathlib.Path, ref: str = "HEAD") -> dict:
    commit, data = build(ref)
    kit = out_dir / "kit"
    kit.mkdir(parents=True, exist_ok=True)
    (kit / f"{commit}.tar.gz").write_bytes(data)
    pointer = {"commit": commit, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (kit / "snapshot.json").write_text(json.dumps(pointer) + "\n", encoding="utf-8")
    return pointer


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    pointer = write(pathlib.Path(argv[0]), os.environ.get("GITHUB_SHA") or "HEAD")
    print(f"kit snapshot {pointer['commit']}: {pointer['bytes']} bytes, sha256 {pointer['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
