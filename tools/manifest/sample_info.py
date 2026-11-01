"""What the kit knows about one sample, read from its folder: one definition, used by ``start.py`` (the samples record
and ``newer``), the developer site's samples index (``site/gallery.py``) and the site's checks (``site/test_site.py``).

    version(folder)        the sample's version: its app.json's, else its manifest's, else its README's newest *Versions* heading
    versions(readme)       the README's *Versions* section: [(version, [lines])], newest first
    industries(readme)     the README's *Industries* line: a list of the App library's industries, or ["every industry"]
    till_lines(readme)     the README's *Try it at the till* lines
    till_part(folder)      whether the sample puts something at the till (a till key, a check, a capture, a module)
    config_pack(folder)    whether the sample is a configuration pack (set in Desk, never ticked into an app)

The README's own words are the source; nothing here is written twice. Standard library only.
"""
from __future__ import annotations

import json
import pathlib
import re

# The App library's twelve industries, in the words the gallery shows (the library's catalogue holds the same)
INDUSTRIES = ("Beauty and cosmetics", "Electronics and phones", "Fashion", "Grocery", "Hardware and DIY", "Hospitality",
              "Liquor and wine", "Optical", "Pharmacy", "Thrift and resale", "Travel retail", "Distribution and warehousing")
EVERY = "every industry"
# Samples that are configuration packs: what they do is set in Desk, so the gallery lists them under *Set in Desk first*
CONFIG_PACKS = frozenset({"s5_config_pack", "s8_estate_rollout"})
# What puts a part of the app at the till: a till key (in the manifest, or answered by the sample's own code at a
# /point/ route), a module, a scan source, field rules on a till theme, sale details the till asks for, or a connection
# point the till calls (a check at Pay, a capture, the payer, a page over the sale). A button in Desk or a document check
# is not at the till.
TILL_KEYS = ("remote_keys", "extension_modules", "scan_sources", "field_rules", "sale_attributes")
POINT_ROUTE = re.compile(r"""["']/point/[a-z_]+""")
TILL_POINTS = frozenset({"check", "capture", "payer", "page"})

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_SECTION = re.compile(r"^## (.+?)\s*$", re.M)
_INDUSTRIES = re.compile(r"^\*\*Industries:\*\*\s*(.+?)\s*$", re.M)


def section(readme: str, title: str) -> str | None:
    """The body of the README's ``## <title>`` section (to the next ``## `` heading), or None."""
    heads = list(_SECTION.finditer(readme))
    for i, h in enumerate(heads):
        if h.group(1).strip().lower() == title.lower():
            end = heads[i + 1].start() if i + 1 < len(heads) else len(readme)
            return readme[h.end():end]
    return None


def _items(body: str) -> list[str]:
    """A section's lines: each bullet (``- ``) with its wrapped continuation, else each plain paragraph line."""
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if s.startswith(("- ", "* ")):
            out.append(s[2:].strip())
        elif out and line.startswith((" ", "\t")):
            out[-1] += " " + s
        else:
            out.append(s)
    return out


def versions(readme: str) -> list[tuple[str, list[str]]]:
    """The *Versions* section as [(version, its lines)], in the README's order (newest first)."""
    body = section(readme, "Versions")
    if body is None:
        return []
    out: list[tuple[str, list[str]]] = []
    for part in re.split(r"^### ", body, flags=re.M)[1:]:
        head, _, rest = part.partition("\n")
        out.append((head.strip(), _items(rest)))
    return out


def industries(readme: str) -> list[str] | None:
    """The *Industries* line's values, or None when the README has no such line."""
    m = _INDUSTRIES.search(readme)
    if not m:
        return None
    text = m.group(1).strip().rstrip(".")
    if text.lower() == EVERY:
        return [EVERY]
    return [p.strip() for p in text.split(",") if p.strip()]


def till_lines(readme: str) -> list[str]:
    body = section(readme, "Try it at the till")
    return _items(body) if body is not None else []


def manifest(folder: pathlib.Path) -> dict | None:
    for p in (folder / "manifest.json", folder / "outside" / "manifest.json"):
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                return None
    return None


def app_json(folder: pathlib.Path) -> dict | None:
    p = folder / "app.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def readme(folder: pathlib.Path) -> str:
    p = folder / "README.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def version(folder: pathlib.Path) -> str | None:
    """The sample's version: its app.json's (the hosting order), else its manifest's, else its newest *Versions* heading."""
    for data in (app_json(folder), manifest(folder)):
        v = (data or {}).get("version")
        if isinstance(v, str) and VERSION.match(v):
            return v
    vs = versions(readme(folder))
    return vs[0][0] if vs and VERSION.match(vs[0][0]) else None


def till_part(folder: pathlib.Path) -> bool:
    m = manifest(folder) or {}
    if any(m.get(k) for k in TILL_KEYS) or any(isinstance(s, dict) and s.get("point") in TILL_POINTS
                                               for s in m.get("extension_subscriptions") or []):
        return True
    return any(POINT_ROUTE.search(p.read_text(encoding="utf-8", errors="ignore")) for p in folder.rglob("*.py")
               if "tests" not in p.relative_to(folder).parts)


def config_pack(folder: pathlib.Path) -> bool:
    return folder.name in CONFIG_PACKS


def vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".")) if isinstance(v, str) and VERSION.match(v) else (0,)
