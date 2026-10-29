"""Make a copied app yours: rename every name its manifest creates to your own prefix, in one step.

Every name an app creates on a shop's site starts with its prefix (``PP BLN Location``), and every field it adds to the
shop's own records starts with its app name (``pp_bln_default_bin``), because names on a site are shared and carry no
owner. A copy of one of our samples or library apps must therefore take your prefix before it reaches a customer: your
company's first word, then one or two words of your own (``ACME BINS`` → the app ``acme_bins``).

    cp -r <the kit>/samples/s2_bins my-bins
    python3 <the kit>/tools/manifest/rename.py my-bins/manifest.json --prefix "ACME BINS"            # shows what changes
    python3 <the kit>/tools/manifest/rename.py my-bins/manifest.json --prefix "ACME BINS" --write    # writes it

It renames the prefix and the app name wherever a string in the manifest carries them (record types, fields, roles,
workspaces, reports, print formats, till keys, feeds, links between them), sets ``app`` and ``prefix``, and then runs the
shop's own checker (``validate.py``) and the install's extra refusals (``site_rules.py``) on the result. It writes
nothing unless every check passes and no old name is left in the manifest.

If an ``app.json`` (the hosting order, chapter 14b) sits beside the manifest, it is renamed too: its ``app`` becomes your
app's address name (``acme-bins`` → ``https://acme-bins.ivendnext.app`` on CitiXsys hosting), and its ``handler`` and
``package`` paths point at the folder your copy is in, relative to your repository's root. A sample's service imports
the kit's app template (``tools/app_template/service``), so your copy lives inside a copy of the kit: a repository made
from the kit, with your app in a folder of its own two levels down (``apps/acme_bins/``).

It does not edit your code. It lists every line of the other files in the manifest's folder that still names the old
prefix or app (a service that reads a record type by name, a test, the README), so you change each one yourself: a
service that takes its prefix from a setting, as the Bin locations service does with ``BLN_PREFIX``, needs only that
setting.

Exit codes: 0 renamed (or shown) · 1 refused · 2 usage.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from site_rules import refusals as site_refusals  # noqa: E402
from validate import RESERVED_PREFIX_WORDS, _PREFIX_RE, app_for, validate  # noqa: E402

TEXT = {".py", ".js", ".mjs", ".ts", ".json", ".md", ".html", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env",
        ".sh", ".j2", ".jinja", ".css", ".zpl", ".sql"}
TEXT_NAMES = {"Dockerfile", "Procfile"}      # text files with no extension: a sample's container recipe names its own folder


def _walk(o, f):
    if isinstance(o, dict):
        return {k: _walk(v, f) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v, f) for v in o]
    return f(o) if isinstance(o, str) else o


def _strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def refuse_prefix(prefix: str, old: str) -> str | None:
    """Why ``prefix`` cannot be used, or None."""
    if not _PREFIX_RE.match(prefix):
        return "the prefix is one to three upper-case words, e.g. 'ACME BINS'"
    if prefix.split()[0] in RESERVED_PREFIX_WORDS:
        return (f"'{prefix.split()[0]}' is a word the shop reads in field names, so no prefix may start with it "
                "(the save rules page lists them all)")
    if prefix == old:
        return "the new prefix is the app's own"
    return None


def case_like(new: str):
    """A substitution that writes ``new`` in the case the match was written in (CSS classes and user names are lower case)."""
    return lambda m: new.lower() if m.group(0).islower() else new


def kit_prefixes() -> set:
    """Every prefix the kit's samples own ("PP RXC"), read from their manifests."""
    found = set()
    for p in [*HERE.parents[1].glob("samples/*/manifest.json"), *HERE.parents[1].glob("samples/*/outside/manifest.json")]:
        try:
            found.add(json.loads(p.read_text(encoding="utf-8"))["prefix"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def role_start(old_p: str) -> re.Pattern | None:
    """The start of a name that begins with the prefix's first word alone ("PP Integration"), a role of this sample. A
    name that begins with another sample's prefix ("PP RXC Rx Number", the counter-rules app's field that S41 reads) is
    that app's, and stays as it is."""
    words = old_p.split()
    if len(words) < 2:
        return None
    rests = [" ".join(words[1:])] + [o.split(" ", 1)[1] for o in kit_prefixes()
                                      if o != old_p and o.split()[0] == words[0] and len(o.split()) > 1]
    return re.compile(rf"^{re.escape(words[0])} (?!(?:{'|'.join(re.escape(r) for r in rests)})\b)")


def encoded(prefix: str) -> str | None:
    """The pattern of ``prefix`` as a web address writes it, its spaces as ``%20`` ("/api/resource/PP%20RFR%20Settings"),
    or None for a one-word prefix. ``%20`` ends in a digit, so a ``%20`` before the prefix is a boundary too."""
    if " " not in prefix:
        return None
    return rf"(?:(?<![A-Za-z0-9])|(?<=%20)){re.escape(prefix.replace(' ', '%20'))}(?![A-Za-z0-9])"


def rename(m: dict, prefix: str) -> tuple[dict, list[str]]:
    """The manifest under ``prefix``, and every string of it that still names the old prefix or app."""
    old_p, old_a, new_a = m["prefix"], m["app"], app_for(prefix)
    names = re.compile(rf"\b{re.escape(old_p)}\b")
    fields = re.compile(rf"(?<![A-Za-z0-9]){re.escape(old_a)}(?=_|\b)")
    # a naming series, a style class or a service user carries the prefix with hyphens ("PP-APR-.YYYY.-", "pp-apr-label"):
    # it becomes yours too, in the case it was written in
    series = re.compile(rf"(?<![A-Za-z0-9]){re.escape(old_p.replace(' ', '-'))}(?=-|\b)", re.I)
    new_s = case_like(prefix.replace(" ", "-"))
    # a web address carries the prefix with its spaces as %20 (a stand-in retailer's path in a test)
    web = re.compile(encoded(old_p), re.I) if encoded(old_p) else None
    new_w = case_like(prefix.replace(" ", "%20"))
    # A sample's shared role ("PP Integration") starts with the prefix's first word only: it becomes yours too
    # ("ACME BINS Integration"), as the App library's own copy names it ("IVENDNEXT BLN Integration").
    first = role_start(old_p)

    # ... and a sentence may name that role or theme in its middle ("The shop must have the role PP Integration"): it
    # follows there too, or the description names a role the manifest no longer has
    shared = sorted({s for s in _strings(m) if first and first.search(s) and len(s) <= 80}, key=len, reverse=True)
    inside = re.compile("|".join(rf"(?<![A-Za-z0-9]){re.escape(r)}(?![A-Za-z0-9])" for r in shared)) if shared else None

    def one(s: str) -> str:
        s = inside.sub(lambda r: first.sub(prefix + " ", r.group(0)), s) if inside else s
        s = series.sub(new_s, fields.sub(new_a, names.sub(prefix, s)))
        s = web.sub(new_w, s) if web else s
        return first.sub(prefix + " ", s) if first else s

    out = _walk(m, one)
    out["app"], out["prefix"] = new_a, prefix
    left = sorted({s for s in _strings(out) if names.search(s) or fields.search(s) or series.search(s)
                                                   or (web and web.search(s)) or (first and first.search(s))
                                                   or (inside and inside.search(s))})
    return out, left


def addresses(m: dict) -> list[str]:
    """Every outside address the manifest names (not a guide page): each one is the original builder's, never yours."""
    seen = []
    for s in _strings(m):
        for u in re.findall(r"https?://[^\s\"'<>]+", s):
            host = re.sub(r"^https?://", "", u).split("/")[0]
            if host not in ("docs.ivendnext.com", "developer.ivendnext.com", "help.ivendnext.com", "www.ivendnext.com") \
                    and u not in seen:
                seen.append(u)
    return seen


def mentions(folder: pathlib.Path, skip: set, old_p: str, old_a: str) -> list[str]:
    """``file:line: text`` for each line outside the manifest that still names the old prefix or app."""
    pat = re.compile(rf"\b{re.escape(old_p)}\b|(?<![A-Za-z0-9]){re.escape(old_a)}(?=_|\b)"
                     rf"|(?<![A-Za-z0-9]){re.escape(old_p.replace(' ', '-'))}(?=-|\b)"
                     + (f"|{encoded(old_p)}" if encoded(old_p) else ""), re.I)
    hits = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p in skip or (p.suffix.lower() not in TEXT and p.name not in TEXT_NAMES) or "__pycache__" in p.parts:
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{p.relative_to(folder)}:{n}: {line.strip()[:120]}" for n, line in enumerate(lines, 1) if pat.search(line)]
    return hits


def kit_root(folder: pathlib.Path) -> pathlib.Path | None:
    """The nearest folder above ``folder`` that holds the kit's app template, or None."""
    for d in [folder, *folder.parents]:
        if (d / "tools" / "app_template" / "service" / "function.py").is_file():
            return d
    return None


def rename_app_json(a: dict, folder: pathlib.Path, root: pathlib.Path | None, new_app: str) -> tuple[dict, list[str]]:
    """The hosting order under the new app: its address name, and its paths at ``folder``. Notes for the reader."""
    out, notes = json.loads(json.dumps(a)), []
    out["app"] = new_app.replace("_", "-")
    old = re.search(r"\b(samples/[^/\s\"']+)/", json.dumps(a))
    if old and root is not None:
        rel = folder.resolve().relative_to(root.resolve()).as_posix()
        if rel.count("/") != 1:
            notes.append(f"your app is at {rel}/: a sample's service finds the kit two folders up, so put it at "
                         "<folder>/<your app>/ (for example apps/acme_bins/)")
        out = _walk(out, lambda s: s.replace(old.group(1) + "/", rel + "/"))
    elif old:
        notes.append("no copy of the kit above this folder: the service imports tools/app_template/service, so put "
                     "your app inside a repository made from the kit")
    return out, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rename a copied app's manifest to your own prefix.")
    ap.add_argument("manifest", type=pathlib.Path, help="the copied app's manifest.json")
    ap.add_argument("--prefix", required=True, help='your prefix: your company\'s first word, then one or two words ("ACME BINS")')
    ap.add_argument("--write", action="store_true", help="write the renamed manifest over the file (otherwise only show)")
    a = ap.parse_args(argv)
    try:
        m = json.loads(a.manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"{a.manifest}: cannot read it as JSON ({e})")
        return 2
    if not isinstance(m, dict) or not isinstance(m.get("prefix"), str) or not isinstance(m.get("app"), str):
        print(f"{a.manifest}: not a manifest (it needs an app and a prefix)")
        return 2
    why = refuse_prefix(a.prefix, m["prefix"])
    if why:
        print(f"REFUSED: {why}")
        return 1
    new, left = rename(m, a.prefix)
    bad = [f"{r['where']} {r.get('name') or ''}: {r['reason']}" for r in validate(new) + site_refusals(new)]
    for line in bad:
        print(f"REFUSED: {line}")
    for s in left:
        print(f"REFUSED: still names {m['prefix']} or {m['app']}: {s[:160]}")
    if bad or left:
        return 1
    before = sum(1 for s in _strings(m) if m["prefix"] in s or m["app"] in s)
    print(f"{m['app']} → {new['app']}: {before} name(s) renamed from '{m['prefix']}' to '{a.prefix}'; the shop's checker "
          "and the install's extra refusals pass on the result")
    # the hosting order beside the manifest, or one folder up when the manifest sits in a folder of its own (S3's outside/)
    up = a.manifest.parent.parent / "app.json" if a.manifest.parent.name == "outside" else a.manifest.parent / "app.json"
    aj = next((p for p in (a.manifest.parent / "app.json", up) if p.is_file()),
              a.manifest.parent / "app.json")
    app_json, notes = None, []
    if aj.is_file():
        try:
            app_json, notes = rename_app_json(json.loads(aj.read_text(encoding="utf-8")), aj.parent,
                                              kit_root(aj.parent), new["app"])
            print(f"app.json: the address name {app_json['app']}, its paths at "
                  f"{(app_json.get('handler') or '').rsplit('/service', 1)[0] or 'your folder'}")
        except (OSError, ValueError) as e:
            print(f"app.json: cannot read it as JSON ({e}); fix it by hand")
    for n in notes:
        print(f"NOTE: {n}")
    if a.write:
        a.manifest.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"written: {a.manifest}")
        if app_json is not None:
            aj.write_text(json.dumps(app_json, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"written: {aj}")
    else:
        print("nothing written (add --write)")
    skip = {a.manifest, aj} if app_json is not None else {a.manifest}
    hits = mentions(aj.parent if app_json is not None else a.manifest.parent, skip, m["prefix"], m["app"])
    if hits:
        print(f"\nStill naming {m['prefix']} or {m['app']} outside the manifest: change each one yourself")
        print("\n".join(f"  {h}" for h in hits))
    urls = addresses(new)
    if urls:
        print("\nOutside addresses in the manifest: put your own service's address in their place")
        print("\n".join(f"  {u}" for u in urls))
    print(f"\nStill yours to change before you deliver it: the lines and addresses above, and the manifest's title "
          f"({m.get('title')!r}), publisher ({m.get('publisher')!r}), version and description. Then: "
          f"python3 <the kit>/tools/check/check.py {a.manifest.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
