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
"""
from __future__ import annotations

import html
import posixpath
import re

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
