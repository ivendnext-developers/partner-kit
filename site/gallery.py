"""site/gallery.py — the cards on "Reference apps and samples" and on the samples list, built from the sample READMEs.

A sample's card is read at site build; nothing generated is committed, so a new sample shows up by itself. What a card shows:

  name, one line   the README's title, and its "When to use it" line (or else its first paragraph)
  door             the doors of the needs cards that cite the sample (the cards win); with no card, the README's own
                   `**Door:**` line, the door's name as needs.py gives it. A card that cites a sample which still has
                   that line is an error: once a card cites it, the line goes
  screenshot       the first still image the README links from its screenshots/ folder (an animated GIF only if there is
                   no still, so nothing plays on load); none, no placeholder
  run it           the first code block under "## Run it" (or "## How to run it"), at most four lines
  links            the sample's page, its folder on GitHub, and the needs it serves

A sample that lacks a run section or a door fails the build. Reference-app cards are written by hand in the page, one
`{{reference-app: …}}` line each, until their repositories are public. A card holds no script; the site's script rules are in build.py's header.

The samples index (samples/index.json on the built site, published at each kit merge) is built here too, from the same cards
and READMEs: per sample its title, when to use it, picture, door, the needs it serves, its recipe, its industries, its
version and Versions lines, its Try it at the till lines, and whether it is a configuration pack. The New app page reads it
for its ways in, and tools/manifest/combine.py's newer() reads it for the notice of newer samples. What a README says is read
by one definition, tools/manifest/sample_info.py. readme_errors() is the build's check of those READMEs: a README with no
Industries line, or one that differs from the census site/industries.json, a sample with a till part and no Try it at the
till section, and a README whose Versions section is missing or whose newest heading is not the sample's version.
"""
from __future__ import annotations

import collections
import html
import json
import pathlib
import posixpath
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "manifest"))
import sample_info  # noqa: E402  (what the kit knows about one sample, read from its folder: one definition)

RUN_HEAD = re.compile(r"^## (?:How to )?run it\s*$", re.I | re.M)
DOOR_LINE = re.compile(r"^\*\*Door:\*\*[ \t]*(.*?)[ \t]*$", re.M)
SHOT = re.compile(r"!\[[^\]]*\]\((screenshots/[^)\s]+)\)")
NO_DOOR = {"request", "none"}                    # a sample shows a door; these two say there is none
STATUSES = ("Brief ready", "Being built", "Ready to copy")


def run_step(text: str) -> tuple[list[str], str]:
    """The first code block under the run section (its first four lines), and the section's heading, or ([], "")."""
    m = RUN_HEAD.search(text)
    if not m:
        return [], ""
    body = re.split(r"^## ", text[m.end():], maxsplit=1, flags=re.M)[0]
    block = re.search(r"^```[^\n]*\n(.*?)^```", body, re.S | re.M)
    lines = [ln for ln in block.group(1).splitlines() if ln.strip()] if block else []
    return lines[:4], m.group().lstrip("# ").strip()


def collect(pages: list, backlinks: dict, doors: dict, first_use, slug, root, errors: list) -> list[dict]:
    """One entry per sample, in the pages' order (S-number): everything its card shows. Faults go to `errors`."""
    by_name = {name.lower(): key for key, name in doors.items()}
    out = []
    for p in pages:
        if p.group != "samples":
            continue
        folder = p.src.removesuffix("/README.md")
        where = f"{p.src}: card:"
        cited = backlinks.get(folder, [])
        by_card = [c for c in cited if c.door not in NO_DOOR]       # a not-yet card names Request: it gives no door
        line = DOOR_LINE.search(p.text)
        keys: list[str] = []
        if by_card:
            keys = [d for d in doors if any(c.door == d for c in by_card)]
            if line:
                errors.append(f"{where} a needs card cites this sample, so its **Door:** line must go (the cards win)")
        elif not line:
            errors.append(f"{where} no needs card with a door cites this sample and it has no **Door:** line")
        else:
            key = by_name.get(line.group(1).strip().lower())
            if key is None or key in NO_DOOR:
                errors.append(f"{where} **Door:** {line.group(1)!r} is not one of the doors' names (Request and None are refused)")
            else:
                keys = [key]
        run, head = run_step(p.text)
        if not run:
            errors.append(f"{where} no `## Run it` section with a code block")
        shots = SHOT.findall(p.text)
        shot = next((s for s in shots if not s.lower().endswith(".gif")), shots[0] if shots else "")
        shot_ok = bool(shot) and (root / folder / shot).is_file()               # a missing file already fails the README's own link
        out.append({"folder": folder, "out": p.out, "title": p.title, "line": (lambda x: x[:1].upper() + x[1:])(first_use(p)), "doors": keys, "run": run,
                    "run_id": slug(head) if head else "", "shot": f"{folder}/{shot}" if shot_ok else "",
                    "needs": len(cited)})
    return out


def card(s: dict, here: str, repo: str, doors: dict, door_pages: set, heading: str = "h3") -> str:
    """One sample's card, with links written from the page in the folder `here`. A door links its needs page when it has one."""
    rel = lambda target: posixpath.relpath(target, here or ".")
    door = ", ".join(f'<a href="{rel(f"needs/door/{d}.html")}">{html.escape(doors[d])}</a>' if d in door_pages
                     else html.escape(doors[d]) for d in s["doors"])
    links = [f'<a href="{rel(s["out"])}#{s["run_id"]}">Run it</a>', f'<a href="{repo}/tree/main/{s["folder"]}">Folder on GitHub</a>']
    if s["needs"]:
        links.append(f'<a href="{rel(s["out"])}#needs-this-serves">Serves {s["needs"]} need{"s" if s["needs"] > 1 else ""}</a>')
    thumb = (f'<a class="thumb" href="{rel(s["out"])}" tabindex="-1" aria-hidden="true"><img src="{rel(s["shot"])}" alt="" '
             f'loading="lazy"></a>' if s["shot"] else "")
    run = "\n".join(html.escape(ln) for ln in s["run"])
    return (f'<li class="card">{thumb}<{heading}><a href="{rel(s["out"])}">{html.escape(s["title"])}</a></{heading}>'
            f'<p>{html.escape(s["line"])}</p><p class="door">Door: {door}</p><pre class="run" tabindex="0"><code>{run}</code></pre>'
            f'<p class="links">{" · ".join(links)}</p></li>')


def flat(samples: list[dict], here: str, repo: str, doors: dict, door_pages: set) -> str:
    return '<ul class="cards">' + "".join(card(s, here, repo, doors, door_pages, "h2") for s in samples) + "</ul>"


def grouped(samples: list[dict], here: str, repo: str, doors: dict, door_pages: set, slug) -> str:
    """The samples under their first door, in the order of needs.py's list, with a list of anchors above. One card each."""
    groups = [(d, [s for s in samples if s["doors"] and s["doors"][0] == d]) for d in doors]
    groups = [(d, mine) for d, mine in groups if mine]
    nav = "".join(f'<li><a href="#{slug(doors[d])}">{html.escape(doors[d])}</a> ({len(mine)})</li>' for d, mine in groups)
    body = "".join(f'<h3 id="{slug(doors[d])}">{html.escape(doors[d])}</h3><ul class="cards">'
                   + "".join(card(s, here, repo, doors, door_pages, "h4") for s in mine) + "</ul>" for d, mine in groups)
    return f'<nav aria-label="Samples by door"><ul class="plain anchors">{nav}</ul></nav>{body}'


def reference_app(spec: str, org_url: str, doors: dict, errors: list, src: str, note: str) -> str:
    """A hand-written reference-app card: `name | one line | doors | status | repository`. Its repository holds BRIEF.md and
    is private for now, so `note` (build.py's NOT_OPEN_YET) sits under its links."""
    parts = [x.strip() for x in spec.split("|")]
    names = {n.lower() for k, n in doors.items() if k not in NO_DOOR}
    if len(parts) != 5 or parts[3] not in STATUSES or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", parts[4]) \
            or not all(d.strip().lower() in names for d in parts[2].split(",")):
        errors.append(f"{src}: a reference app needs `name | one line | doors | status | repository`: doors by their names, "
                      f"status one of {', '.join(STATUSES)}, a repository name")
        return ""
    name, line, door_text, status, repo = parts
    base = f"{org_url}/{repo}"
    return (f'<li class="card"><h3>{html.escape(name)}</h3><p>{html.escape(line)}</p><p class="door">Doors: {html.escape(door_text)}</p>'
            f'<p class="status">{html.escape(status)}</p><p class="links"><a href="{base}">The repository</a> · '
            f'<a href="{base}/blob/main/BRIEF.md">BRIEF.md</a></p><p class="note">{html.escape(note[:1].upper() + note[1:])}.</p></li>')


# ── the samples index and the check of what it is read from ────────────────────────────────────────────────────────
CENSUS = "site/industries.json"
RECIPE_LINK = re.compile(r"\]\(((?:\.\./)+recipes/[a-z0-9_]+\.md)\)|`(recipes/[a-z0-9_]+\.md)`")   # a link, or a kit path in code
GENERIC_RECIPES = {"recipes/make_it_your_own.md"}           # every README names it: it is how to start, not the sample's recipe


def census(root) -> dict:
    return json.loads((pathlib.Path(root) / CENSUS).read_text("utf-8"))


def census_industries(name: str, data: dict) -> list[str] | None:
    """The industries the census lists the sample under, in the App library's order; ["every industry"] when it lists it
    under none and among every_industry; None when it lists it nowhere."""
    mine = [i for i in sample_info.INDUSTRIES if name in (data.get("industries") or {}).get(i, [])]
    if mine:
        return mine
    return [sample_info.EVERY] if name in (data.get("every_industry") or []) else None


def readme_errors(root) -> list[str]:
    """The build's check of the sample READMEs the index is read from. Each message names the README."""
    root = pathlib.Path(root)
    errors: list[str] = []
    try:
        data = census(root)
    except (OSError, ValueError) as e:
        return [f"{CENSUS}: cannot be read ({e})"]
    folders = sorted(p.parent for p in (root / "samples").glob("*/README.md"))
    names = {f.name for f in folders}
    listed = {s for i in (data.get("industries") or {}).values() for s in i}
    if set(data.get("industries") or {}) != set(sample_info.INDUSTRIES):
        errors.append(f"{CENSUS}: its industries must be the App library's twelve: {', '.join(sample_info.INDUSTRIES)}")
    errors += [f"{CENSUS}: {s} is under an industry and also under every_industry; a sample of every industry is listed under none"
               for s in sorted(listed & set(data.get("every_industry") or []))]
    errors += [f"{CENSUS}: names {s}, which is not a sample folder with a README" for s in sorted((listed | set(data.get("every_industry") or [])) - names)]
    for folder in folders:
        where = f"samples/{folder.name}/README.md"
        text = (folder / "README.md").read_text("utf-8")
        want = census_industries(folder.name, data)
        got = sample_info.industries(text)
        if want is None:
            errors.append(f"{where}: {CENSUS} lists this sample under no industry and not under every_industry")
        if got is None:
            errors.append(f"{where}: no **Industries:** line. Write the line {CENSUS} gives it: "
                          f"**Industries:** {', '.join(want or ['every industry'])}")
        elif want is not None and sorted(got) != sorted(want):
            errors.append(f"{where}: **Industries:** {', '.join(got)} differs from {CENSUS}, which gives {', '.join(want)}")
        if sample_info.till_part(folder) and not sample_info.till_lines(text):
            errors.append(f"{where}: the sample puts a part at the till, so its README needs a ## Try it at the till section "
                          "with what to try, one line each")
        versions = sample_info.versions(text)
        version = sample_info.version(folder)
        if not versions:
            errors.append(f"{where}: no ## Versions section with a ### heading for each version")
        elif versions[0][0] != version:
            errors.append(f"{where}: the newest heading of ## Versions is {versions[0][0]}, but the sample's version is {version}")
    return errors


def recipe_of(folder: str, text: str, cited: list, root) -> str | None:
    """The sample's recipe, as a kit path: the recipe its needs cards cite most (on a tie, one that names the sample's folder,
    then the first cited); with no card naming one, the recipe its README names that also names the sample's folder."""
    def names_it(rel: str) -> bool:
        f = pathlib.Path(root) / rel
        return f.is_file() and re.search(re.escape(folder) + r"\b", f.read_text("utf-8")) is not None
    counts = collections.Counter(r for c in cited for r in c.paths("recipe") if r.startswith("recipes/"))
    if counts:
        order = list(counts)
        return max(order, key=lambda r: (counts[r], names_it(r), -order.index(r)))
    for link, named in RECIPE_LINK.findall(text):
        rel = posixpath.normpath(posixpath.join(folder, link)) if link else named
        if rel not in GENERIC_RECIPES and names_it(rel):
            return rel
    return None


def index(samples: list[dict], pages: list, backlinks: dict, doors: dict, root) -> dict:
    """The published samples index: one entry per sample card, in the cards' order (S-number)."""
    texts = {p.src.removesuffix("/README.md"): p.text for p in pages if p.group == "samples"}
    out = []
    for s in samples:
        folder, text = s["folder"], texts[s["folder"]]
        path = pathlib.Path(root) / folder
        cited = backlinks.get(folder, [])
        recipe = recipe_of(folder, text, cited, root)
        out.append({"name": path.name, "title": s["title"], "version": sample_info.version(path),
                    "versions": [{"version": v, "lines": lines} for v, lines in sample_info.versions(text)],
                    "when_to_use": s["line"] or None, "picture": s["shot"] or None,
                    "door": doors[s["doors"][0]] if s["doors"] else None,
                    "needs": [c.id for c in cited], "recipe": recipe.removesuffix(".md") + ".html" if recipe else None,
                    "industries": sample_info.industries(text) or [], "till": sample_info.till_lines(text),
                    "config_pack": sample_info.config_pack(path)})
    return {"about": "Every kit sample, read from its README at the kit merge this site was built from: the New app page's "
                     "ways in and the notice of newer sample versions read it. picture and recipe are paths on this site; "
                     "needs are the ids of the needs cards (catalogue.json) that cite the sample.",
            "samples": out}
