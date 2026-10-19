#!/usr/bin/env python3
"""licence — the intake's licence check: what an app we list or host must say about its licence and third-party code.

    python3 tools/check/licence.py <app folder> [--hosted]     # exit 0 = ready, 1 = refused, 2 = usage

Every app listed in the App library, or hosted by CitiXsys, carries two files, in its folder or in a folder above it
up to the repository's root (the folder holding ``.git``):

  * a licence file (``LICENSE``, ``LICENCE`` or ``COPYING``, optionally ``.md`` or ``.txt``), filled in: not empty, and
    not the app template's placeholder; you choose the licence;
  * a list of the third-party components it ships (``THIRD_PARTY.md``, ``THIRD_PARTY.txt`` or ``NOTICE``), one line
    per component with its licence, or the word ``None``.

``--hosted`` adds the rule for an app CitiXsys runs for you: a component under the GNU Affero GPL is accepted only
when you publish its source, so its line must carry the ``https://`` address where that source is published. The
component lines are the list's items or table rows (``- …``, ``| … |``); a list with none is read line by line. Bounds:
the address is read, not visited, so it must be the component's source, not its licence's text; and a component's
licence belongs on its own line, since a licence on a line below it is not read.

The App library's publish command (``tools/publish``) runs this on your project; ``tools/deploy_app`` runs it with ``--hosted``.
Standard library only. Read-only. A green line is not legal advice: you answer for your app's licences (the partner
terms).
"""
from __future__ import annotations

import pathlib
import re
import sys

LICENCE_FILES = [b + e for b in ("LICENSE", "LICENCE", "COPYING") for e in ("", ".md", ".txt")]
LIST_FILES = ["THIRD_PARTY.md", "THIRD_PARTY.txt", "NOTICE", "NOTICE.md", "NOTICE.txt"]
PLACEHOLDER = "REPLACE THIS FILE WITH YOUR APP'S LICENCE"
AGPL = re.compile(r"\bAGPL|Affero", re.I)
SOURCE = re.compile(r"https://\S+")
ENTRY = re.compile(r"[-*+|]|\d+[.)]\s")  # a list item or a table row: one component


def _find(folder: pathlib.Path, names: list[str]) -> pathlib.Path | None:
    """The first of ``names`` in ``folder`` or a folder above it, up to the repository's root; a folder in no
    repository (an unpacked order, say) is searched alone, so a file far above it is never taken for the app's."""
    chain = [folder, *folder.parents]
    root = next((i for i, here in enumerate(chain) if (here / ".git").exists()), 0)
    for here in chain[:root + 1]:
        for n in names:
            if (here / n).is_file():
                return here / n
    return None


def check(folder, hosted: bool = False) -> list[str]:
    """The refusals for an app folder; an empty list means it passes."""
    folder = pathlib.Path(folder).resolve()
    bad = []
    lic = _find(folder, LICENCE_FILES)
    if lic is None:
        bad.append("no licence file: add LICENSE (your choice of licence) to your app's folder or its repository's root")
    else:
        text = lic.read_text("utf-8", errors="replace")
        if not text.strip():
            bad.append(f"{lic.name} is empty: fill in your app's licence")
        elif PLACEHOLDER in text.upper():
            bad.append(f"{lic.name} is still the template's placeholder: replace it with your app's licence")
    lst = _find(folder, LIST_FILES)
    if lst is None:
        bad.append("no list of third-party components: add THIRD_PARTY.md, one line per component with its licence, "
                   "or the word None")
        return bad
    lines = [ln.strip() for ln in lst.read_text("utf-8", errors="replace").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]  # a heading alone lists nothing
    if not lines:
        bad.append(f"{lst.name} is empty: one line per third-party component with its licence, or the word None")
    if hosted:
        entries = [ln for ln in lines if ENTRY.match(ln)] or lines
        for ln in entries:
            if AGPL.search(ln) and not SOURCE.search(ln):
                bad.append(f"{lst.name}: an AGPL component is hosted only when you publish its source; put the "
                           f"https:// address of that source on its line: {ln[:80]}")
    return bad


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    hosted = "--hosted" in argv
    rest = [a for a in argv if a != "--hosted"]
    if len(rest) != 1 or not pathlib.Path(rest[0]).is_dir():
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    bad = check(rest[0], hosted)
    for b in bad:
        print("REFUSED: " + b)
    print("licence: " + ("ready" if not bad else f"{len(bad)} refusal(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
