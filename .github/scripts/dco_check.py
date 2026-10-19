#!/usr/bin/env python3
"""DCO check: every commit a pull request adds must carry a `Signed-off-by: Name <email>` line (git commit -s).

    python3 .github/scripts/dco_check.py <base-ref> [<head-ref>]       # exit 0 = every commit is signed off

Merge commits are skipped. Reads only the local git history; no network, no secret.
"""
from __future__ import annotations

import re
import subprocess
import sys

SIGNED = re.compile(r"^Signed-off-by: .+ <[^<>\s]+@[^<>\s]+>\s*$", re.M)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base, head = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "HEAD")
    shas = subprocess.run(["git", "rev-list", "--no-merges", f"{base}..{head}"], capture_output=True, text=True, check=True).stdout.split()
    unsigned = []
    for sha in shas:
        msg = subprocess.run(["git", "log", "-1", "--format=%B", sha], capture_output=True, text=True, check=True).stdout
        if not SIGNED.search(msg):
            unsigned.append(sha[:10] + " " + msg.strip().split("\n")[0][:70])
    for u in unsigned:
        print("NOT SIGNED OFF: " + u)
    print(f"DCO: {len(shas)} commit(s) checked, " + ("all signed off" if not unsigned else f"{len(unsigned)} without a sign-off (git commit -s --amend, or git rebase --signoff)"))
    return 1 if unsigned else 0


if __name__ == "__main__":
    sys.exit(main())
