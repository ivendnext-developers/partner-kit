#!/usr/bin/env python3
"""Run every test folder of the kit and fail if any test fails — or if a folder runs no test at all.

    python3 .github/scripts/run_tests.py            # from anywhere

It DISCOVERS the folders (any `tests/` directly under `samples/<name>/` or `tools/<name>/`), so a later change that adds a
sample or a tool with tests needs no edit here or in the CI workflow. The two checks that are not unittest folders are
listed in EXTRA. Needs only Python 3.10+ and the standard library (S29's template tests also use jinja2, which CI installs and which they skip without); no network, no secret. A test that needs a private
stand-in or a recorded bench run skips itself and says so; the skip count is printed so a rise is visible.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXTRA = [("tools/selfcheck --self-test", ["python3", "tools/selfcheck/selfcheck.py", "--self-test"])]


def folders() -> list[pathlib.Path]:
    found = sorted(p for pat in ("samples/*/tests", "tools/*/tests") for p in ROOT.glob(pat) if p.is_dir())
    return [p for p in found if any(p.glob("test_*.py"))]


def main() -> int:
    env = dict(os.environ, PARTNER_KIT=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    bad, total = 0, 0
    jobs = [(str(d.relative_to(ROOT)), ["python3", "-m", "unittest", "discover", "-s", str(d.relative_to(ROOT)), "-p", "test_*.py"])
            for d in folders()] + EXTRA
    for name, cmd in jobs:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        out = r.stdout + r.stderr
        ran = re.findall(r"Ran (\d+) tests?", out)
        skip = re.findall(r"skipped=(\d+)", out)
        n = int(ran[-1]) if ran else 0
        total += n
        ok = r.returncode == 0 and (n > 0 or name in dict(EXTRA))
        bad += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name:46} ran={n:<4} skipped={skip[-1] if skip else 0}")
        if not ok:
            print("     " + "\n     ".join(out.strip().split("\n")[-20:]))
    print(f"\n{len(jobs)} test jobs, {total} tests: " + ("ALL GREEN" if not bad else f"{bad} FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
