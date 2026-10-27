#!/usr/bin/env python3
"""Start from one of the kit's samples under your own name, in one command.

    python3 tools/manifest/start.py s11_approvals --prefix "ACME APR"

It copies ``samples/s11_approvals`` into ``apps/acme_apr/`` of your repository (a repository made from the kit: the
sample's service finds the kit two folders up), makes the app yours the way ``rename.py`` does (the manifest, and the
hosting order beside it), and then also rewrites, in the sample's code, tests and README, every line ``rename.py``
would only list. It finishes only when no name of the sample is left anywhere in the copy, and then runs the kit's own
checks (``tools/check/check.py``) over it. If anything fails, the copy is removed: you get a finished app or nothing.

Your prefix is your company's first word, then one or two words of your own (``ACME APR``, from ``ACME``); the first
word is the one iVendNext registered for you. ``--into`` is the repository to put the app in (default: the kit this
tool sits in); ``--test`` also runs the copied tests under the new names.

What it leaves for you, as ``rename.py`` does: the manifest's title, publisher, version and description, the outside
addresses in the manifest, and the sample's settings named after the sample (``APR_PREFIX``: the name of a setting
is yours to keep, its default is already your prefix). The sample's screenshots are not copied: they show our
placeholder names, not yours, and the pictures are taken out of the README.

It reads only the sample and writes only the new folder under ``apps/``. It calls no network and reads no secret.
Exit codes: 0 done · 1 refused · 2 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
KIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import rename  # noqa: E402
from validate import app_for  # noqa: E402

OURS = ("PP", "IVENDNEXT")           # ours: never a partner's first word (the library refuses it too)
WORD = re.compile(r"[A-Z][A-Z0-9]{1,11}")   # a maker's first word, as the library holds it (lower case there)
IMAGE = re.compile(r"!\[[^\]]*\]\(screenshots/[^)]*\)")
SKIP_DIRS = {"__pycache__", "screenshots"}
START_LINE = "*Start from this sample:"      # an italic line, so the site does not take it for the page's description


class Refused(Exception):
    pass


def manifest_of(sample: pathlib.Path) -> pathlib.Path:
    for p in (sample / "manifest.json", sample / "outside" / "manifest.json"):
        if p.is_file():
            return p
    raise Refused(f"{sample.name} has no manifest.json of its own (it builds its manifests, or is not an app): "
                  "copy it by hand as its README says")


def refuse_new_prefix(prefix: str, old: str) -> None:
    why = rename.refuse_prefix(prefix, old)
    if not why:
        first = prefix.split()[0]
        if first in OURS:
            why = f"'{first}' is ours (iVendNext's and the samples'): use your own company's first word"
        elif not WORD.fullmatch(first):
            why = f"'{first}' is not a first word the library holds: two to twelve capital letters or digits, starting with a letter"
    if why:
        raise Refused(why)


def texts(root: pathlib.Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and (p.suffix.lower() in rename.TEXT or p.name in rename.TEXT_NAMES):
            yield p


def old_names(m: dict, sample: str = "") -> re.Pattern:
    """Every spelling of the sample's prefix and app name, any case: spaced, hyphened (a naming series), as a web address
    writes it (``PP%20RFR``), snake. With the
    sample's folder name, also its path in the kit (``samples/s34_po_check``): a container recipe built from the repository's
    root would otherwise still build the kit's sample."""
    o, a = m["prefix"], m["app"]
    forms = [rf"\b{re.escape(o)}\b", rf"(?<![A-Za-z0-9]){re.escape(o.replace(' ', '-'))}(?=-|\b)",
             rf"(?<![A-Za-z0-9]){re.escape(a)}(?=_|\b)"]
    if rename.encoded(o):
        forms.append(rename.encoded(o))
    if sample:
        forms.append(rf"samples/{re.escape(sample)}\b")
    # the roles and themes named with the prefix's first word alone ("PP Integration"), wherever a line names them
    forms += [rf"(?<![A-Za-z0-9]){re.escape(r)}(?![A-Za-z0-9])" for r in roles(m)]
    return re.compile("|".join(forms), re.I)


def roles(m: dict) -> set:
    """The manifest's names that start with the prefix's first word alone ("PP Integration"): ``rename`` makes them yours."""
    words = m["prefix"].split()
    if len(words) < 2:
        return set()
    first = re.compile(rf"^{re.escape(words[0])} (?!{re.escape(' '.join(words[1:]))}\b)")
    return {s for s in rename._strings(m) if first.search(s) and len(s) <= 80}


def rewrite(text: str, m: dict, prefix: str, sample: str, app: str) -> str:
    """One file's text under the new names: what ``rename`` does to a manifest string, plus the roles that start with the
    old first word alone, the sample's own folder and the README's pictures."""
    old_p, old_a = m["prefix"], m["app"]
    text = re.sub(rf"\b{re.escape(old_p)}\b", prefix, text)
    text = re.sub(rf"\b{re.escape(old_p)}\b", rename.case_like(prefix), text, flags=re.I)          # a note, "pp exm: ..."
    text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old_p.replace(' ', '-'))}(?=-|\b)",
                  rename.case_like(prefix.replace(" ", "-")), text, flags=re.I)
    if rename.encoded(old_p):                                                                 # a stand-in's path, "PP%20RFR"
        text = re.sub(rename.encoded(old_p), rename.case_like(prefix.replace(" ", "%20")), text, flags=re.I)
    text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old_a)}(?=_|\b)", rename.case_like(app), text, flags=re.I)
    for old in sorted(roles(m), key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])", re.sub(r"^\S+", prefix, old, count=1), text)
    return text.replace(f"samples/{sample}", f"apps/{app}").replace("](../s", "](../../samples/s")   # links to the other samples


def run(sample: str, prefix: str, into: pathlib.Path, test: bool, out) -> int:
    src = KIT / "samples" / sample
    if not re.fullmatch(r"[A-Za-z0-9_]+", sample) or not src.is_dir():
        raise Refused(f"no sample called {sample} in {KIT / 'samples'}")
    mpath = manifest_of(src)
    m = json.loads(mpath.read_text(encoding="utf-8"))
    refuse_new_prefix(prefix, m["prefix"])
    into = into.resolve()
    if rename.kit_root(into) != into:
        raise Refused(f"{into} is not a repository made from the kit (it has no tools/app_template/service): your app "
                      "goes in apps/<your app>/ of a copy of the kit, because the sample's service finds the kit two folders up")
    app = app_for(prefix)
    target = into / "apps" / app
    if target.exists():
        raise Refused(f"apps/{app} exists already: pick another short name, or move that folder away")
    made_apps = not (into / "apps").exists()
    try:
        shutil.copytree(src, target, ignore=lambda d, names: [n for n in names if n in SKIP_DIRS or n.endswith(".pyc")])
        return finish(src, target, m, mpath.relative_to(src), prefix, sample, app, into, test, out)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        if made_apps:
            with contextlib.suppress(OSError):
                (into / "apps").rmdir()
        raise


def finish(src, target, m, mrel, prefix, sample, app, into, test, out) -> int:
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        rc = rename.main([str(target / mrel), "--prefix", prefix, "--write"])
    if rc:
        raise Refused("\n".join(l for l in log.getvalue().splitlines() if l.startswith("REFUSED")) or log.getvalue())
    renames = int((re.search(r"(\d+) name\(s\) renamed", log.getvalue()) or [0, 0])[1])
    done = {mrel.as_posix(), "app.json"}                       # rename.main wrote these
    other = 0
    for p in texts(target):
        rel = p.relative_to(target).as_posix()
        old = p.read_text(encoding="utf-8")
        new = old
        if rel not in done:
            if p.name == "README.md" and p.parent == target:
                new = IMAGE.sub("", "\n".join(l for l in old.split("\n") if not l.startswith(START_LINE)))
            new = rewrite(new, m, prefix, sample, app)
        if new != old:
            p.write_text(new, encoding="utf-8")
            done.add(rel)
            other += 1
    for p in sorted(target.rglob("*.json")):
        try:
            other_pkg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (isinstance(other_pkg, dict) and isinstance(other_pkg.get("prefix"), str) and isinstance(other_pkg.get("app"), str)
                and other_pkg["prefix"] != prefix and p.relative_to(target) != mrel):
            raise Refused(f"{p.relative_to(target).as_posix()} is a second package with its own prefix ({other_pkg['prefix']}): "
                          "one prefix cannot rename two packages, so copy this sample by hand as its README says")
    left = leftovers(target, m, sample)
    if left:
        raise Refused("a name of the sample is still in the copy, so it is not finished:\n  " + "\n  ".join(left))
    for p in sorted(q for q in target.rglob("*") if q.is_file()):
        rel = p.relative_to(target).as_posix()
        print(f"  {'rewritten' if rel in done else 'copied   '}  apps/{app}/{rel}", file=out)
    files = sum(1 for q in target.rglob("*") if q.is_file())
    print(f"{sample} → apps/{app}: {files} file(s) written, {renames} name(s) in the manifest renamed from "
          f"'{m['prefix']}' to '{prefix}', {other} other file(s) rewritten, 0 old names left", file=out)
    shots = sum(1 for q in (src / "screenshots").rglob("*") if q.is_file()) if (src / "screenshots").is_dir() else 0
    if shots:
        print(f"the sample's {shots} screenshot(s) were not copied (they show our names, not yours)", file=out)
    kit = subprocess.run([sys.executable, "-I", str(KIT / "tools" / "check" / "check.py"), str(target)],
                         capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    verdict = (kit.stdout.strip().splitlines() or ["(no verdict)"])[-1]
    print(f"the kit's checks over apps/{app}: {verdict}", file=out)
    if kit.returncode:
        raise Refused(f"the kit's checks refuse the copy:\n{kit.stdout}{kit.stderr}")
    if test:
        t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], cwd=target,
                           capture_output=True, text=True,
                           env=dict({k: v for k, v in os.environ.items() if not k.startswith(("IVN_", "LIBRARY_"))},
                                    PARTNER_KIT=str(into), PYTHONDONTWRITEBYTECODE="1"))      # no key of yours reaches the tests
        ran = (re.findall(r"^Ran (\d+) tests?", t.stderr, re.M) or ["0"])[-1]
        print(f"the copied tests: ran {ran}, {'OK' if t.returncode == 0 else 'FAILED'}", file=out)
        if t.returncode:
            raise Refused("the copied tests fail under the new names:\n" + t.stderr[-1500:])
    else:
        print(f"run its tests: python3 -m unittest discover -s apps/{app}/tests -p 'test_*.py'", file=out)
    print(f"Still yours to change: the manifest's title ({m.get('title')!r}), publisher, version and description, and any "
          "outside address in it.", file=out)
    return 0


def leftovers(target: pathlib.Path, m: dict, sample: str) -> list[str]:
    pat = old_names(m, sample)
    found = [f"{p.relative_to(target).as_posix()}: the file's own name" for p in target.rglob("*")
             if pat.search(p.relative_to(target).as_posix())]
    for p in texts(target):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                found.append(f"{p.relative_to(target).as_posix()}:{n}: {line.strip()[:100]}")
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Copy one of the kit's samples under your own prefix, ready to build on.")
    ap.add_argument("sample", help="the sample's folder name, e.g. s11_approvals")
    ap.add_argument("--prefix", required=True, help='your company\'s first word, then one or two words ("ACME APR")')
    ap.add_argument("--into", type=pathlib.Path, default=KIT, help="the repository made from the kit to put the app in (default: this kit)")
    ap.add_argument("--test", action="store_true", help="also run the copied tests under the new names")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        return run(a.sample, a.prefix, a.into, a.test, sys.stdout)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 1
    except UnicodeDecodeError as e:
        print(f"REFUSED: a file of the sample is not UTF-8 text ({e.reason}); nothing was left behind: copy this sample by hand")
        return 1


if __name__ == "__main__":
    sys.exit(main())
