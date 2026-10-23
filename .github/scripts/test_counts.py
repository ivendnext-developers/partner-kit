#!/usr/bin/env python3
"""Every test count a README states is the count its tests run, so a README never says 32 where 33 run.

    python3 .github/scripts/test_counts.py --self-test     # each planted fault red; run_tests.py runs it too

It is used by run_tests.py, which runs every test folder through ``run`` below and then hands what ran to ``check``:
nothing runs twice. ``run <folder>`` is ``python3 -m unittest discover -s <folder> -p 'test_*.py'`` with the same output
and exit code, and one more line last, ``COUNTS {...}``: the tests run and skipped, per test file.

A claim is read in one of these forms; a count written any other way is not checked:
  * ``N laptop tests``, ``N tests that run on a laptop``, ``laptop tests (N)``;
  * after ``**Laptop:**`` or ``**On the laptop:**``, the first ``N tests`` on that line;
  * ``**Laptop, N tests**``;
  * ``# N tests`` at the end of a line (a comment after the command that runs them).
A claim in a table row whose first cell is ``tests/test_<name>.py`` counts that file; any other counts the whole folder.
A count matches when it equals the tests run, or the tests run less those skipped (a test that replays a recorded bench
run skips without one, and READMEs count it either way).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import unittest

FORMS = [re.compile(p) for p in (
    r"\b(\d+) laptop tests\b",
    r"\b(\d+) tests that run on a laptop\b",
    r"\blaptop tests \((\d+)\)",
    r"\*\*(?:On the laptop|Laptop):\*\*.*?\b(\d+) tests\b",
    r"\*\*Laptop, (\d+) tests\*\*",
    r"#\s*(\d+) tests\s*$",
)]
FILE_ROW = re.compile(r"^\|\s*`tests/(test_\w+\.py)`\s*\|")


def claims(text: str) -> list[tuple[int, str | None, int]]:
    """``(line, test file or None for the whole folder, count)`` for each count the text states."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        row = FILE_ROW.match(line)
        for form in FORMS:
            for m in form.finditer(line):
                out.append((i, row.group(1) if row else None, int(m.group(1))))
    return out


def check(root: pathlib.Path, counts: dict) -> list[str]:
    """Each README claim that does not match. ``counts``: ``{"samples/s9_bi_feed": {"test_s9.py": [ran, skipped]}}``."""
    bad = []
    for folder, files in sorted(counts.items()):
        readme = root / folder / "README.md"
        if not readme.is_file():
            continue
        for line, name, n in claims(readme.read_text("utf-8")):
            if name is None:
                ran, skipped = (sum(v[0] for v in files.values()), sum(v[1] for v in files.values()))
                where = "its tests"
            elif name in files:
                ran, skipped = files[name]
                where = f"tests/{name}"
            else:
                bad.append(f"{folder}/README.md:{line}: names tests/{name}, which ran no test")
                continue
            if n not in (ran, ran - skipped):
                runs = f"{ran}" + (f" ({skipped} skipped)" if skipped else "")
                bad.append(f"{folder}/README.md:{line}: says {n}, {where} ran {runs}")
    return bad


class _Result(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.per_file = {}

    def _file(self, test):
        return type(test).__module__.rsplit(".", 1)[-1] + ".py"

    def startTest(self, test):
        super().startTest(test)
        self.per_file.setdefault(self._file(test), [0, 0])[0] += 1

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.per_file.setdefault(self._file(test), [0, 0])[1] += 1


def run(folder: str) -> int:
    sys.path[0] = os.getcwd()                      # as `python3 -m unittest` has it: the working folder, not this one's
    suite = unittest.TestLoader().discover(folder, pattern="test_*.py")
    result = unittest.TextTestRunner(resultclass=_Result).run(suite)
    print("COUNTS " + json.dumps(result.per_file, sort_keys=True))
    if not result.testsRun:
        return 5                                   # as unittest's own exit for a folder with no test
    return 0 if result.wasSuccessful() else 1


def self_test() -> int:
    import tempfile
    readme = ("| `tests/test_a.py` | 3 laptop tests against a fake shop |\n"
              "| `tests/test_b.py` | laptop tests (2): the rest |\n"
              "- **Laptop:** the tests above (6 tests, 1 more that replays a bench run; 4 canaries)\n"
              "python3 -m unittest discover -s x/tests     # 7 tests\n")
    good = {"test_a.py": [3, 0], "test_b.py": [2, 0], "test_c.py": [2, 1]}
    planted = {
        "a file one test short": ({**good, "test_a.py": [4, 0]}, "README.md:1: says 3, tests/test_a.py ran 4"),
        "a second file grown": ({**good, "test_b.py": [3, 0]}, "README.md:2: says 2, tests/test_b.py ran 3"),
        "the folder grown": ({**good, "test_c.py": [3, 1]}, "README.md:3: says 6, its tests ran 8 (1 skipped)"),
        "a named file gone": ({k: v for k, v in good.items() if k != "test_b.py"}, "names tests/test_b.py, which ran no test"),
    }
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / "s").mkdir()
        (pathlib.Path(d) / "s" / "README.md").write_text(readme, "utf-8")
        got = check(pathlib.Path(d), {"s": good})
        fails += bool(got)
        print(("FAIL" if got else "OK  ") + " the counts as stated pass" + (f": {got}" if got else ""))
        for what, (counts, want) in planted.items():
            got = check(pathlib.Path(d), {"s": counts})
            red = any(want in g for g in got)
            fails += not red
            print(("OK  " if red else "FAIL") + f" {what} is red" + ("" if red else f": got {got}"))
    seen = [c[2] for c in claims(readme)]
    if seen != [3, 2, 6, 7]:
        fails += 1
        print(f"FAIL the four forms read as [3, 2, 6, 7], not {seen}")
    print("SELF-TEST " + ("GREEN" if not fails else f"RED ({fails})"))
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"] and len(sys.argv) == 3:
        sys.exit(run(sys.argv[2]))
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(__doc__)
