#!/usr/bin/env python3
"""site/pdf/build_pdfs.py — the site's branded PDFs, built from the kit's own files at every Site run and never committed.

    python3 site/pdf/build_pdfs.py [SITE_OUT]        # default: site/_out; writes SITE_OUT/downloads/*.pdf

Run it after site/build.py (which empties SITE_OUT) and before check_links.py. It needs headless Chrome, found at $CHROME,
else at the usual places on a Mac or on Linux; without one it fails and says how to set CHROME, never skips. No other tool:
the checks below read the PDF with the standard library.

The PDFs (DOCS below):
  blueprint_form.pdf          the project blueprint as a form to print, read from kit/blueprint_template.md: the status
                              choices are tick boxes from the needs catalogue's STATUSES; at most 4 A4 pages, the integration
                              map on a landscape page.
  blueprint_how_to_fill.pdf   kit/blueprint.md's "How to fill it" (its steps, the four verdicts, the doors) and every door of
                              the catalogue by its build step (site/build.py BUILD_ORDER); exactly 1 page.
  blueprint_example.pdf       kit/blueprint_example.md in the form's own layout: its answers printed, the chosen boxes ticked
                              (a choice cell ticks on its first word; a Status cell must be a verdict word exactly); at most
                              5 pages, the integration map on a landscape page.
  ladder_and_four_rules.pdf   guide chapter 3's "The ladder" and "The four rules" sections, one sheet front and back: exactly
                              2 pages, so a section that outgrows its page fails the build.
  needs_at_a_glance.pdf       every card of the needs catalogue, by area and A to Z in the customer's words: the verdict and
                              the door; at most 6 pages. Each row carries its card's id, and the ids must be the cards', once each.

How: each PDF is an HTML page built in a temporary folder with print.css, the brand's Inter (fonts/) and the site's logo;
it is never published. Its links are written absolute (https://developer.ivendnext.com/… for a site page, the GitHub address
build.py makes for a kit file), because a relative link would point at the temporary file. Chrome prints it with
--print-to-pdf; the header, the page numbers and the footer are @page margin boxes. Before printing, the page is laid out
on screen at the content width (170 mm portrait, 257 mm landscape) and every box is measured, the way
kit/design/tools/check_page.py measures with --dump-dom.

A PDF is refused (the build fails and nothing is written for it) when it:
  - does not start with %PDF- or end with %%EOF;
  - holds /JavaScript, /JS, /Launch, /EmbeddedFile, /GoToR, /SubmitForm, /ImportData or /RichMedia (names written with #xx
    escapes are read as a reader reads them), in a dictionary or in a stream that is not a font or an image;
  - has a font that is not embedded, or an embedded font whose name is not Inter (a system fallback);
  - has a link that is not https to developer.ivendnext.com or to github.com/ivendnext-developers (so a file: link fails);
  - has more pages than its budget (or, for an exact budget, any other count);
  - had a box past its page's content edge, or wider than its table cell, when measured;
and the form (blank or filled) is refused when it does not show every status word of the catalogue, the example when a
choice cell ticks no box, and needs at a glance when its card ids are not the catalogue's, once each.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from urllib.parse import urljoin, urlsplit

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build  # noqa: E402  (render, section, collect, Ctx and the needs catalogue the site is built from)

catalogue = build.catalogue
BASE = f"https://{build.DOMAIN}/"
TEMPLATE = "kit/blueprint_template.md"
EXAMPLE = build.EXAMPLE
LADDER = "guide/03_ladder_and_never_list.md"
LADDER_SECTIONS = ("The ladder", "The four rules — what every build keeps, and why")
GUIDE = "kit/blueprint.md"
HOWITWORKS = "guide/01a_how_it_all_works.md"          # chapter 1a, How it all works: the whole chapter, its pictures beside it
DATA_TRAVELS = "guide/01c_how_the_data_travels.md"
CHROME_PLACES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome",
                 "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser")
LINK_HOSTS = {"developer.ivendnext.com": "/", "github.com": "/ivendnext-developers/"}     # host: the path a link must start with
FORBIDDEN = ("JavaScript", "JS", "Launch", "EmbeddedFile", "GoToR", "SubmitForm", "ImportData", "RichMedia")
CONTENT_MM = {"portrait": 170, "landscape": 257}                 # A4 less 20 mm each side

# The form's layout, by section letter. Each width list must have one width (mm) per column of the template's table, and
# add up to the page's content width; a template table that changes its columns fails the build until this is updated.
WIDTHS = {"b": [7, 39, 22, 45, 22, 35], "c": [80, 45, 45], "d": [24, 20, 20, 32, 26, 28, 30, 28, 49], "e": [70, 30, 70],
          "f": [7, 55, 25, 45, 38]}
ROW_MM = {"b": 11, "c": 7.5, "d": 13, "e": 9, "f": 11}            # the writing height of a row
BLANK_ROWS = {"b": 12, "d": 8, "f": 8}                           # an empty table prints this many ruled rows
LANDSCAPE = {"d"}
TICKS = {"Basis (counted / estimated)": ["counted", "estimated"], "On / off": ["On", "Off"]}   # plus Status, from STATUSES


class Doc:
    """One PDF: its file name, header title, page budget (`exact`: exactly that many), body maker, landscape page count,
    body class (print.css: "" is the brand's 10 pt body; "guide" the compact one-page style) and the site page its footer names."""
    def __init__(self, name: str, title: str, pages: int, exact: bool, make, landscape: int = 0, cls: str = "",
                 home: str = "kit/blueprint.html"):
        self.name, self.title, self.pages, self.exact, self.make, self.landscape, self.cls = name, title, pages, exact, make, landscape, cls
        self.home = home


# ── the kit's text, as print HTML ──────────────────────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    return html.escape(text, quote=True)


def table_rows(text: str) -> list[list[str]]:
    """The rows of the Markdown tables in `text` (the separator row dropped), each a list of its cells."""
    rows = []
    for ln in text.splitlines():
        if ln.startswith("|") and not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+\s*", ln):
            rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def parse_template(text: str) -> tuple[list[list[str]], list[dict]]:
    """(the field rows under the title, the sections (a)–(f): letter, title, hints (a paragraph in italics), the other
    paragraphs (a filled section's answer) and table rows)."""
    head, *parts = re.split(r"^## ", text, flags=re.M)
    sections = []
    for part in parts:
        title, _, body = part.partition("\n")
        m = re.match(r"\(([a-z])\) ", title)
        paras = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("|")]
        hints = [p.strip("*") for p in paras if re.fullmatch(r"\*[^*].*[^*]\*", p, re.S)]
        sections.append({"letter": m.group(1) if m else "", "title": title.strip(), "hints": hints,
                         "text": [p for p in paras if p.strip("*") not in hints], "rows": table_rows(body)})
    return table_rows(head)[1:], sections


def inline(text: str) -> str:
    """A filled answer's few marks: **bold** and *italics*; everything else printed as written."""
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text)))


def ticks(options, picked: str | None = None) -> str:
    options = list(options)
    boxes = "".join(f'<span class="opt{" on" if o == picked else ""}"><span class="tick{" on" if o == picked else ""}"></span>{esc(o)}</span>'
                    for o in options)
    return f'<span class="opts">{boxes}</span>' if len(options) > 3 else boxes


def choice(cell: str, options: list[str], exact: bool, where: str, errors: list) -> str:
    """A choice cell: its boxes, the chosen one ticked, the rest of the cell after them as a note. A Status cell (`exact`)
    must be a verdict word exactly; any other ticks on its first word, case ignored (*estimated from last year* ticks
    *estimated*). An empty cell is a blank form's: its boxes, none ticked."""
    if not cell:
        return ticks(options)
    first = re.match(r"[\w'-]+", cell)
    word = first.group().lower() if first else ""
    picked = (cell if cell in options else None) if exact else next((o for o in options if o.split()[0].lower() == word), None)
    if picked is None:
        errors.append(f"{where}: {cell!r} ticks none of the boxes ({' · '.join(options)})")
        return ticks(options)
    rest = cell[len(picked):] if cell.lower().startswith(picked.lower()) else cell[first.end():]
    rest = rest.lstrip(" ,;:—–-")
    return ticks(options, picked) + (f'<span class="note">{esc(rest)}</span>' if rest else "")


def field_rows(fields: list[list[str]], project: str = "", errors: list | None = None) -> str:
    """The header block: the project (the template's own heading, "Blueprint:" and its name), then each field with its
    answer, which a blank form leaves empty."""
    out = [f'<tr><th>Project</th><td>{esc(project)}</td></tr>']
    for label, *answer in fields:
        m = re.match(r"\*\*(.+?)\*\*\s*(?:\((.+)\))?$", label)
        name, hint = (m.group(1), m.group(2) or "") if m else (label, "")
        answer = answer[0] if answer else ""
        if hint.startswith("one of:"):
            options = [o.strip() for o in hint[7:].split("·")]
            out.append(f"<tr><th>{esc(name)}</th><td>{choice(answer, options, False, f'the field {name}', errors if errors is not None else [])}</td></tr>")
        else:
            out.append(f'<tr><th>{esc(name)}{f"<span class=sub>{esc(hint)}</span>" if hint else ""}</th><td>{esc(answer)}</td></tr>')
    return '<table class="fields">' + "".join(out) + "</table>"


def form_table(sec: dict, statuses: dict, errors: list, src: str = TEMPLATE) -> str:
    letter, (header, *rows) = sec["letter"], sec["rows"]
    widths = WIDTHS.get(letter, [])
    page = CONTENT_MM["landscape" if letter in LANDSCAPE else "portrait"]
    if len(widths) != len(header) or sum(widths) != page:
        errors.append(f"{src} ({letter}): {len(header)} columns; site/pdf/build_pdfs.py WIDTHS has {len(widths)} "
                      f"adding up to {sum(widths)} mm, not {page}")
        return ""
    choices = {i: (list(statuses.values()) if h == "Status" else TICKS[h]) for i, h in enumerate(header) if h == "Status" or h in TICKS}
    if all(not any(r[1:] if header[0] == "#" else r) for r in rows):    # an empty table: ruled rows to write in, numbered
        rows = [[str(n) if header[0] == "#" else ""] + [""] * (len(header) - 1) for n in range(1, BLANK_ROWS.get(letter, 6) + 1)]
    cols = "".join(f'<col style="width:{w}mm">' for w in widths)
    head = "".join(f"<th>{esc(h.split(' (')[0] if i in choices else h)}</th>" for i, h in enumerate(header))
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            if i in choices:
                cells.append(f"<td>{choice(c, choices[i], header[i] == 'Status', f'{src} ({letter}) row {r[0]}, {header[i]}', errors)}</td>")
            elif header[i] == "Card":                                 # a card id breaks at its hyphens, not mid-word
                cells.append(f'<td class="id">{esc(c)}</td>')
            elif i == 0 and c:
                cells.append(f'<td class="{"num" if header[0] == "#" else "fixed"}">{esc(c)}</td>')
            else:
                cells.append(f"<td>{esc(c)}</td>")
        body.append(f'<tr style="height:{ROW_MM.get(letter, 9)}mm">' + "".join(cells) + "</tr>")
    return f'<table class="form"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def band(title: str, lede: str) -> str:
    return f'<div class="band"><img src="logo-band.svg" alt="iVendNext"><h1>{esc(title)}</h1><p>{lede}</p></div>'


def form_body(errors: list, statuses: dict | None = None, src: str = TEMPLATE) -> str:
    """The blueprint form, from kit/blueprint_template.md; or, given the filled example, that example in the same layout:
    its answers printed and its choices ticked, its band naming the retailer and saying it is invented."""
    statuses = statuses if statuses is not None else catalogue.STATUSES
    text = (build.ROOT / src).read_text("utf-8")
    fields, sections = parse_template(text)
    if src == TEMPLATE:
        title, project = "Project blueprint", ""
        lede = (f'How to fill it: <a href="{BASE}downloads/blueprint_how_to_fill.pdf">the one-page guide</a> and '
                f'<a href="{BASE}kit/blueprint.html">the blueprint page</a>. To fill it on screen: '
                f'<a href="{BASE}kit/blueprint_template.html">the template</a>. Filled in: '
                f'<a href="{BASE}downloads/blueprint_example.pdf">the example</a>.')
    else:
        m = re.match(r"# (Blueprint example — (.+))\n", text)
        invented = next((p.strip().strip("*") for p in text.split("## ")[0].split("\n\n")[1:2]), "")
        if not m or "invented" not in invented:
            errors.append(f"{src}: it must open with '# Blueprint example — ⟨name⟩' and a line saying the company is invented")
        title, project = (m.group(1), m.group(2)) if m else ("Blueprint example", "")
        lede = (f'{esc(invented)} The blank form: <a href="{BASE}downloads/blueprint_form.pdf">blueprint_form.pdf</a>; '
                f'how to fill it: <a href="{BASE}downloads/blueprint_how_to_fill.pdf">the one-page guide</a>.')
    out = [band(title, lede), field_rows(fields, project, errors)]
    for sec in sections:
        part = [f"<h2>{esc(sec['title'])}</h2>"] + [f'<p class="hint">{esc(h)}</p>' for h in sec["hints"]]
        if sec["rows"]:
            part.append(form_table(sec, statuses, errors, src))
        elif not sec["text"]:
            part.append('<div class="lines"><div></div><div></div><div></div></div>')
        part += [f'<p class="answer">{inline(p)}</p>' for p in sec["text"]]
        out.append(f'<section class="wide">{"".join(part)}</section>' if sec["letter"] in LANDSCAPE else "".join(part))
    return "".join(out)


def example_body(errors: list, statuses: dict | None = None) -> str:
    """The filled example, kit/blueprint_example.md, in the form's own layout."""
    return form_body(errors, statuses, EXAMPLE)


def ladder_body(errors: list) -> str:
    """The ladder and the four rules: guide chapter 3's two sections, one to a page (print.css breaks before the second)."""
    ctx = kit_ctx(errors)
    ctx.src, ctx.out = LADDER, "guide/03_ladder_and_never_list.html"
    parts = []
    for heading, cls in zip(LADDER_SECTIONS, ("ladder", "rules")):
        text = build.section(LADDER, heading)
        if not text:
            errors.append(f"{LADDER}: no section {heading!r}")
        parts.append(f'<section class="sheet {cls}"><h2>{esc(heading)}</h2>{absolute(build.render(text, ctx, {}, None), ctx.out)}</section>')
    lede = (f'Guide chapter 3 on one sheet: the ladder on the front, the four rules on the back. The whole chapter: '
            f'<a href="{BASE}{ctx.out}">developer.ivendnext.com/{ctx.out}</a>.')
    return band("The ladder and the four rules", lede) + "".join(parts)


def chapter_pictures(src: str) -> list[str]:
    """The pictures a kit chapter shows from its own img/ folder (drawn inline in its print HTML, never fetched)."""
    return re.findall(r"!\[[^\]]*\]\(img/([\w.-]+\.svg)\)", (build.ROOT / src).read_text("utf-8"))


def howitworks_body(errors: list) -> str:
    """How iVendNext apps work: guide chapter 1a whole, its pictures printed from the print folder, never fetched."""
    ctx = kit_ctx(errors)
    ctx.src, ctx.out = HOWITWORKS, "guide/01a_how_it_all_works.html"
    text = (build.ROOT / HOWITWORKS).read_text("utf-8")
    head, _, rest = text.partition("\n## ")
    if not rest:
        errors.append(f"{HOWITWORKS}: no sections")
    body = absolute(build.render("## " + rest, ctx, {}, None), ctx.out)
    for name in chapter_pictures(HOWITWORKS):                  # each picture drawn in the page itself, so its words print in Inter
        svg = (build.ROOT / "guide" / "img" / name).read_text("utf-8")
        tag = name.removesuffix(".svg")
        svg = svg.replace('id="t"', f'id="{tag}-t"').replace('id="d"', f'id="{tag}-d"').replace(
            'aria-labelledby="t d"', f'aria-labelledby="{tag}-t {tag}-d"')
        body = re.sub(rf'<img src="{re.escape(BASE)}guide/img/{re.escape(name)}"[^>]*>', lambda m: svg, body)
    lede = (f'Guide chapter 1a: what an iVendNext app is, where it runs, where the customer\'s data lives, why customers never '
            f'collide, and what publishing and hosting hand over. Online, with every link: '
            f'<a href="{BASE}{ctx.out}">developer.ivendnext.com/{ctx.out}</a>.')
    return band("How iVendNext apps work", lede) + f'<div class="chapter">{body}</div>'


def inline_svg(m) -> str:
    """A guide picture written into the page itself, so its words are set in the page's own Inter (an image's are not) and it
    is as wide as the column; its title and description stay, for a reader that cannot see it."""
    svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", (build.ROOT / "guide" / "img" / m.group(1)).read_text("utf-8"))
    svg = re.sub(r'font-family="[^"]*"', 'font-family="Inter"', svg, count=1)
    k = m.group(1).rsplit(".", 1)[0]                       # three pictures in one page: their title and description ids apart
    svg = svg.replace('aria-labelledby="t d"', f'aria-labelledby="t-{k} d-{k}"').replace('id="t"', f'id="t-{k}"').replace('id="d"', f'id="d-{k}"')
    return re.sub(r'\swidth="[\d.]+" height="[\d.]+"', ' width="100%"', svg, count=1)


def data_travels_body(errors: list) -> str:
    """Guide chapter 1c whole, its pictures written into the page (inline_svg: the light ones, as print is light); the chapter's
    own *Download* line is left out (the PDF does not link itself)."""
    ctx = kit_ctx(errors)
    ctx.src, ctx.out = DATA_TRAVELS, "guide/01c_how_the_data_travels.html"
    text = (build.ROOT / DATA_TRAVELS).read_text("utf-8")
    title, _, rest = text.partition("\n")
    rest = re.sub(r"^\*\*Download:\*\*.*$", "", rest, flags=re.M)
    body = absolute(build.render(rest, ctx, {}, None), ctx.out)
    body, n = re.subn(r'<img src="' + re.escape(BASE) + r'guide/img/([\w.-]+\.svg)"[^>]*>', inline_svg, body)
    body = re.sub(r'src="' + re.escape(BASE) + r'guide/img/(1c-[\w.-]+\.png)"', r'src="\1"', body)   # its screenshots: stage()
    if not n:
        errors.append(f"{DATA_TRAVELS}: no picture of the chapter's in its print")
    lede = (f'Guide chapter 1c: two links to outside systems, a chain\'s own loyalty system and a telecom company, traced hop by '
            f'hop, with two chains in the same second. Online, with its samples: '
            f'<a href="{BASE}{ctx.out}">developer.ivendnext.com/{ctx.out}</a>.')
    return band("How the data travels", lede) + f'<section class="chapter travels">{body}</section>'


def glance_body(errors: list) -> str:
    """Every card, by area and A to Z in the customer's words: the verdict and the door's name. Each row carries its card's id."""
    cards = catalogue.load(build.ROOT)
    lede = (f'Every need in the catalogue, read from its cards at this build: what the customer asks, the verdict, and the door '
            f'it is built through. <em>Ready, with limits (3)</em>: three limits to tell the customer. Each card in full: '
            f'<a href="{BASE}needs/index.html">developer.ivendnext.com/needs/</a>.')
    out = [band("Needs at a glance", lede)]
    for a, name in catalogue.AREAS.items():
        rows = "".join(f'<tr data-id="{esc(c.id)}"><td>{esc(c.asks)}</td><td>{esc(c.verdict)}</td><td>{esc(build.door_name(c.door))}</td></tr>'
                       for c in build.by_asks([c for c in cards if c.area == a]))
        if rows:
            out.append(f'<h2 class="area">{esc(name)}</h2><table class="glance"><colgroup><col><col style="width:34mm"><col style="width:34mm">'
                       f"</colgroup><thead><tr><th>The customer asks</th><th>Verdict</th><th>Door</th></tr></thead><tbody>{rows}</tbody></table>")
    return "".join(out)


def missing_answers(body: str, src: str = EXAMPLE) -> list[str]:
    """What the filled example's PDF must print and does not: its retailer's name, its line saying the company is invented,
    and each field's answer (a choice answer as its ticked box)."""
    text = (build.ROOT / src).read_text("utf-8")
    fields, _ = parse_template(text)
    m = re.match(r"# Blueprint example — (.+)\n", text)
    want = [m.group(1)] if m else ["the retailer's name"]
    want += [p.strip().strip("*") for p in text.split("## ")[0].split("\n\n")[1:2]]
    shown = html.unescape(re.sub(r"<[^>]+>", " ", body))
    missing = [w for w in want if w not in shown]
    if m and f"<tr><th>Project</th><td>{esc(m.group(1))}</td></tr>" not in body:
        missing.append(f"the Project row: {m.group(1)!r}")
    for label, *answer in fields:
        a = answer[0] if answer else ""
        if not a:
            missing.append(f"the field {label}: no answer in {src}")
        elif "one of:" in label:                                # ticked by the same rule as the form's: choice()
            options = [o.strip() for o in label.split("one of:")[1].rstrip(")").split("·")]
            if choice(a, options, False, "", []) not in body:
                missing.append(f"the field {label}: {a!r} is not ticked")
        elif a not in shown:
            missing.append(f"the field {label}: {a!r}")
    return missing


def glance_problems(body: str, cards: list) -> list[str]:
    """Needs at a glance against the catalogue: every card listed once, and no row whose id no card has."""
    ids = re.findall(r'<tr data-id="([^"]*)"', body)
    known = {c.id for c in cards}
    return ([f"the card {i} is not listed" for i in sorted(known - set(ids))]
            + [f"the row {i} names no card" for i in sorted(set(ids) - known)]
            + [f"the card {i} is listed {ids.count(i)} times" for i in sorted({i for i in ids if ids.count(i) > 1})])


def kit_ctx(errors: list) -> "build.Ctx":
    """A link context like the site build's: a kit page links its site page, any other kit file its GitHub address."""
    pages = build.collect()
    registry: dict = {p.src: p for p in pages}
    registry.update({posixpath.dirname(p.src): p for p in pages if p.src.endswith("/README.md")})
    for src, out in (("needs/README.md", "needs/index.html"), ("needs", "needs/index.html"),
                     ("recipes", "recipes/index.html"), ("samples", "samples/index.html")):
        registry[src] = build.ListPage(out, "")
    registry.update({c.rel: build.ListPage(f"needs/{c.area}/{c.id}.html", "") for c in catalogue.load(build.ROOT)})
    return build.Ctx(registry, pathlib.Path(tempfile.gettempdir()), errors, set())


def absolute(piece: str, page_out: str) -> str:
    """Every href and src in `piece` (written for the site page `page_out`) as an absolute address."""
    return re.sub(r'\b(href|src)="([^"]*)"', lambda m: f'{m.group(1)}="{esc(urljoin(BASE + page_out, html.unescape(m.group(2))))}"', piece)


def guide_body(errors: list) -> str:
    """How to fill the blueprint: the section of kit/blueprint.md, then every door by the step it is built in."""
    ctx = kit_ctx(errors)
    ctx.src, ctx.out = GUIDE, "kit/blueprint.html"
    text = build.section(GUIDE, "How to fill it")
    if not text:
        errors.append(f"{GUIDE}: no section 'How to fill it'")
    steps = absolute(build.render(text, ctx, {}, None), ctx.out)
    rows = "".join(f"<tr><td><strong>{esc(', '.join(name for d, name in catalogue.DOORS.items() if d in doors))}</strong></td>"
                   f"<td>{esc(why)}</td></tr>" for doors, why in build.BUILD_ORDER)
    lede = (f'For the <a href="{BASE}downloads/blueprint_form.pdf">blueprint form</a> and '
            f'<a href="{BASE}kit/blueprint_template.html">its template</a>. The full guide: '
            f'<a href="{BASE}kit/blueprint.html">kit/blueprint.html</a>; filled in: '
            f'<a href="{BASE}kit/blueprint_example.html">the example</a>.')
    return (band("How to fill the project blueprint", lede) + "<h2>How to fill it</h2>" + steps
            + "<h2>Every door a row can name, by the step it is built in</h2>"
            + '<table><colgroup><col style="width:72mm"><col></colgroup><thead><tr><th>Doors</th><th>When</th></tr></thead>'
            + f"<tbody>{rows}</tbody></table>")


DOCS = [Doc("blueprint_form.pdf", "Project blueprint", 4, False, form_body, landscape=1),
        Doc("blueprint_how_to_fill.pdf", "How to fill the project blueprint", 1, True, guide_body, cls="guide"),
        Doc("blueprint_example.pdf", "Blueprint example", 5, False, example_body, landscape=1, home="kit/blueprint_example.html"),
        Doc("ladder_and_four_rules.pdf", "The ladder and the four rules", 2, True, ladder_body, home="guide/03_ladder_and_never_list.html"),
        Doc("needs_at_a_glance.pdf", "Needs at a glance", 6, False, glance_body, home="needs/index.html"),
        Doc("how_ivendnext_apps_work.pdf", "How iVendNext apps work", 10, False, howitworks_body, home="guide/01a_how_it_all_works.html"),
        Doc("how_the_data_travels.pdf", "How the data travels", 13, False, data_travels_body,
            home="guide/01c_how_the_data_travels.html")]
FORMS = (form_body, example_body)                                 # the documents whose Status boxes must be every verdict word


def kit_sha() -> str:
    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    if not sha:
        r = subprocess.run(["git", "-C", str(build.ROOT), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True)
        sha = r.stdout.strip() if r.returncode == 0 else ""
    return sha or "a local copy"


def css_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def page(doc_title: str, body: str, cls: str = "", home: str = "kit/blueprint.html") -> str:
    """The print HTML: print.css, then this document's own words in the margin boxes (the footer names the site page `home`)."""
    foot = f"{build.DOMAIN}/{home} · Built from kit {kit_sha()}"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(doc_title)}</title>'
            f'<link rel="stylesheet" href="print.css"><style>@page {{ @top-left {{ content: url("logo-header.svg"); }} '
            f"@top-right {{ content: {css_string(doc_title)}; }} @bottom-left {{ content: {css_string(foot)}; }} }} "
            "@page :first { @top-left { content: none; } @top-right { content: none; } }</style>"
            f'</head><body class="{cls}">{body}{WARM}</body></html>')


# Chrome loads a weight of a web font only when the body's text uses it; the margin boxes do not ask for one. So every page
# carries one line, of no height, in each weight the margin boxes use; without it they fall back to a system font (refused).
WARM = '<p class="warm" aria-hidden="true">' + "".join(f'<span style="font-weight:{w}">Page 1</span>' for w in (400, 600, 700, 800)) + "</p>"


# ── Chrome: find it, measure the boxes, print ─────────────────────────────────────────────────────────────────────────
def chrome() -> str:
    found = os.environ.get("CHROME") or next((p for p in CHROME_PLACES if os.access(p, os.X_OK)), "")
    if not found or not os.access(found, os.X_OK):
        raise SystemExit(f"PDF BUILD FAILED: no headless Chrome{' at ' + found if found else ''}. Set CHROME to its path, "
                         "for example CHROME=/usr/bin/google-chrome (the Site workflow sets it).")
    return found


def stage(tmp: pathlib.Path) -> None:
    """The print folder: print.css, the fonts, the logo for the blue band and a small one for the running header."""
    shutil.copy(HERE / "print.css", tmp / "print.css")
    shutil.copytree(HERE / "fonts", tmp / "fonts", dirs_exist_ok=True)
    on_dark = (build.SITE / "assets-src" / "logo-on-dark.svg").read_text("utf-8")      # on the blue band: the logo reversed,
    swap = {'fill="#0089ff"': 'fill="#fff"', 'fill="#fff"': 'fill="#0089ff"'}          # its blue parts white, its white blue
    (tmp / "logo-band.svg").write_text(re.sub(r'fill="#(?:0089ff|fff)"', lambda m: swap[m.group()], on_dark), "utf-8")
    logo = (build.SITE / "assets-src" / "logo.svg").read_text("utf-8")
    (tmp / "logo-header.svg").write_text(re.sub(r'width="[\d.]+" height="[\d.]+"', 'width="84" height="15.1"', logo, count=1), "utf-8")
    for shot in (build.ROOT / "guide" / "img").glob("1c-*.png"):         # chapter 1c's screenshots, loaded from the print folder
        shutil.copy(shot, tmp / shot.name)


PROBE = """<style>body{width:170mm}.wide{width:257mm}</style><script>(function () {
  function run() {
    var rows = [], els = document.body.querySelectorAll("*");
    for (var i = 0; i < els.length; i++) {
      var e = els[i], t = e.tagName;
      if (t === "SCRIPT" || t === "STYLE" || e instanceof SVGElement) continue;
      var box = (e.closest(".wide") || document.body).getBoundingClientRect(), r = e.getBoundingClientRect();
      var name = t.toLowerCase() + (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\\s+/).join(".") : "");
      var text = (e.textContent || "").trim().slice(0, 40);
      if (r.width > 0 && (r.right > box.right + 0.5 || r.left < box.left - 0.5))
        rows.push(name + " runs past the content edge (" + Math.round(r.right - box.right) + "px): " + text);
      if ((t === "TD" || t === "TH") && e.scrollWidth > e.clientWidth + 1)
        rows.push(name + " holds content wider than its cell: " + text);
    }
    var pre = document.createElement("pre"); pre.id = "ivn-probe"; pre.textContent = JSON.stringify(rows);
    document.body.appendChild(pre);
  }
  window.addEventListener("load", function () { document.fonts.ready.then(function () { setTimeout(run, 100); }); });
})();</script>"""


def measure(page_html: str, tmp: pathlib.Path) -> list[str]:
    """What runs past the content edge (170 mm, or 257 mm on the landscape page) or out of its cell, laid out on screen."""
    copy = tmp / "measure.html"
    copy.write_text(page_html.replace("</body>", PROBE + "</body>"), "utf-8")
    try:
        out = subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                              f"--user-data-dir={tmp / 'profile'}", "--virtual-time-budget=5000", "--window-size=1200,1600",
                              "--dump-dom", copy.as_uri()], capture_output=True, text=True, timeout=120).stdout
    except subprocess.TimeoutExpired:
        return ["Chrome did not finish laying out the page in 120 s (the measure did not run)"]
    m = re.search(r'<pre id="ivn-probe">(.*?)</pre>', out, re.S)
    return json.loads(html.unescape(m.group(1))) if m else ["the measure did not run (no probe output from Chrome)"]


def print_pdf(page_html: str, tmp: pathlib.Path) -> bytes:
    src, pdf = tmp / "print.html", tmp / "print.pdf"
    src.write_text(page_html, "utf-8")
    pdf.unlink(missing_ok=True)
    try:                                                          # its own profile folder: no lock shared with another Chrome
        subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=5000",
                        f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={pdf}", src.as_uri()],
                       capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return b""                                                # reported as "Chrome wrote no PDF"
    return pdf.read_bytes() if pdf.is_file() else b""


# ── the PDF checks (standard library only) ────────────────────────────────────────────────────────────────────────
def objects(data: bytes) -> list[tuple[bytes, bytes | None]]:
    """(dictionary, raw stream or None) of each object, the stream cut by its /Length so binary never reads as syntax."""
    found, i = [], 0
    obj = re.compile(rb"\d+\s+\d+\s+obj\b")
    while (m := obj.search(data, i)):
        j = m.end()
        end, st = data.find(b"endobj", j), re.compile(rb"stream\r?\n").search(data, j)
        if st and (end < 0 or st.start() < end):
            head = data[j:st.start()]
            ln = re.search(rb"/Length\s+(\d+)(?!\s+\d+\s+R)", head)        # Chrome writes direct lengths; else: up to endstream
            size = int(ln.group(1)) if ln else -1
            stop = st.end() + size if size >= 0 else data.find(b"endstream", st.end())
            found.append((head, data[st.end():stop]))
            i = max(stop, st.end())
        else:
            found.append((data[j:end if end >= 0 else len(data)], None))
            i = end + 6 if end >= 0 else len(data)
    return found


def names(raw: bytes) -> bytes:                                   # /Java#53cript reads as /JavaScript in a reader
    return re.sub(rb"/[^\s/<>\[\]()]*", lambda m: re.sub(rb"#([0-9A-Fa-f]{2})", lambda h: bytes([int(h.group(1), 16)]), m.group()), raw)


def pdf_string(raw: bytes) -> str:
    """A PDF string token, literal (with its escapes) or hex, as text."""
    raw = raw.strip()
    if raw.startswith(b"<"):
        return bytes.fromhex(re.sub(rb"\s", b"", raw[1:-1]).decode()).decode("latin-1")
    body, out, k = raw[1:-1], bytearray(), 0
    while k < len(body):
        c = body[k]
        if c == 0x5C and k + 1 < len(body):
            n = body[k + 1:k + 2]
            octal = re.match(rb"[0-7]{1,3}", body[k + 1:k + 4])
            if octal:
                out.append(int(octal.group(), 8) & 0xFF)
                k += 1 + len(octal.group())
                continue
            out += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(n, n)
            k += 2
            continue
        out.append(c)
        k += 1
    return out.decode("latin-1")


def link_allowed(uri: str) -> bool:
    try:
        u = urlsplit(uri)
        port = u.port
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    path = u.path or "/"
    return u.scheme == "https" and port in (None, 443) and host in LINK_HOSTS and (path + "/").startswith(LINK_HOSTS[host])


A4 = (595, 842)                                                   # points, rounded


def page_sizes(data: bytes) -> list[tuple[int, int]]:
    """Each page's size in points (width, height), from its /MediaBox, rounded."""
    sizes = []
    for d, _ in objects(data):
        d = names(d)
        if re.search(rb"/Type\s*/Page(?![A-Za-z])", d):
            box = re.search(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]", d)
            x0, y0, x1, y1 = (float(v) for v in box.groups()) if box else (0, 0, 0, 0)
            sizes.append((round(x1 - x0), round(y1 - y0)))
    return sizes


def pdf_problems(data: bytes, pages: int, exact: bool = False, landscape: int = 0) -> list[str]:
    """Why this PDF must not be published (an empty list: it may). `landscape`: how many of its pages must be A4 landscape,
    so a layout Chrome shrank to fit a portrait page (the landscape page not honoured) is refused, not published small."""
    bad = []
    if not data.startswith(b"%PDF-"):
        bad.append("it does not start with %PDF-")
    if not data.rstrip().endswith(b"%%EOF"):
        bad.append("it does not end with %%EOF (cut short)")
    objs = objects(data)
    dicts = [names(d) for d, _ in objs] + [names(data[data.rfind(b"endobj") + 6:])]     # and the trailer
    for d, s in objs:                                             # a stream an action could hide in: not a font, not an image
        if s is None or re.search(rb"/Length[123]|/Subtype\s*/(Image|Type1C|CIDFontType0C|OpenType)", d):
            continue
        try:
            dicts.append(names(zlib.decompress(s) if b"/FlateDecode" in d else s))
        except zlib.error:
            dicts.append(names(s))
    found = sorted({w for d in dicts for w in FORBIDDEN if re.search(rb"/" + w.encode() + rb"(?![A-Za-z0-9])", d)})
    bad += [f"it holds /{w}" for w in found]
    sizes = page_sizes(data)
    count = len(sizes)
    if count > pages or (exact and count != pages):
        bad.append(f"it has {count} pages; its budget is {'exactly ' if exact else 'at most '}{pages}")
    if any(s not in (A4, A4[::-1]) for s in sizes):
        bad.append(f"a page is not A4: {sorted(set(sizes))}")
    if sum(1 for s in sizes if s == A4[::-1]) != landscape:
        bad.append(f"it has {sum(1 for s in sizes if s == A4[::-1])} landscape pages, not {landscape}")
    for d in dicts:
        if re.search(rb"/Type\s*/FontDescriptor", d):
            name = re.search(rb"/FontName\s*/([^\s/<>\[\]()]+)", d)
            name = name.group(1).decode("latin-1") if name else "?"
            if not re.search(rb"/FontFile[23]?\b", d):
                bad.append(f"font {name} is not embedded")
            if not re.fullmatch(r"(?:[A-Z]{6}\+)?Inter(?:-\w+)?", name):
                bad.append(f"font {name} is not Inter (a fallback font was used)")
        elif re.search(rb"/Type\s*/Font\b", d):
            sub = re.search(rb"/Subtype\s*/(\w+)", d)
            sub = sub.group(1).decode() if sub else "?"
            base = re.search(rb"/BaseFont\s*/([^\s/<>\[\]()]+)", d)
            if sub == "Type3" or (sub != "Type0" and b"/FontDescriptor" not in d):
                bad.append(f"font {base.group(1).decode('latin-1') if base else sub} ({sub}) is not an embedded Inter")
        for m in re.finditer(rb"/URI\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", d, re.S):
            uri = pdf_string(m.group(1))
            if not link_allowed(uri):
                bad.append(f"it links {uri[:80]}, which is not https on developer.ivendnext.com or github.com/ivendnext-developers")
        if re.search(rb"/URI(?!\s*[(<])", re.sub(rb"/S\s*/URI\b", b"", d)):           # the action's type, /S /URI, is not an address
            bad.append("it has a link whose address is not a plain string")
    return bad


def word_problems(page_html: str) -> list[str]:
    """The kit's word rules over what the PDF will say: no upstream product or framework name (ruled 2026-10-16: not in any
    kit file, even in code), and "extension point" written in full. The kit's files pass scan_kit.py; this holds the words the
    builder itself writes, and what it reads, as printed."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", page_html))
    bad = [f"it names {m.group()!r}, an upstream name the kit never uses" for m in re.finditer(r"fr[a]ppe|erp[n]ext", text, re.I)]
    return bad + [f"it says {m.group()!r}: write \"extension point\" in full" for m in re.finditer(r"\b(?:an?|the|new|each)\s+points?\b", text, re.I)]


def fetched(page_html: str) -> list[str]:
    """What the print HTML would load from anywhere but the print folder (an image of a kit page is absolute after absolute())."""
    return [u for u in re.findall(r'\bsrc="([^"]*)"|url\(\s*["\']?([^"\')]+)', page_html) for u in u if u and re.match(r"[a-z][a-z0-9+.-]*:|//", u, re.I)
            and not u.startswith("data:")]


def missing_statuses(form_html: str, statuses: dict) -> list[str]:
    """The catalogue's status words the form does not show as a tick box."""
    return [w for w in statuses.values() if not re.search(f'<span class="tick( on)?"></span>{re.escape(esc(w))}</span>', form_html)]


# ── the build ─────────────────────────────────────────────────────────────────────────────────────────────────────
def build_pdfs(out_dir: pathlib.Path) -> int:
    errors: list[str] = []
    made = []
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        stage(tmp)
        for doc in DOCS:
            body = doc.make(errors)
            if doc.make in FORMS:
                errors += [f"{doc.name}: the status {w!r} has no tick box" for w in missing_statuses(body, catalogue.STATUSES)]
            if doc.make is example_body:
                errors += [f"{doc.name}: it does not print {w}" for w in missing_answers(body)]
            if doc.make is glance_body:
                errors += [f"{doc.name}: {p}" for p in glance_problems(body, catalogue.load(build.ROOT))]
            text = page(doc.title, body, doc.cls, doc.home)
            errors += [f"{doc.name}: {w}" for w in word_problems(text)]
            errors += [f"{doc.name}: it would fetch {u} while printing; a PDF is printed from the print folder only"
                       for u in fetched(text)]
            errors += [f"{doc.name}: {p}" for p in measure(text, tmp)]
            data = print_pdf(text, tmp)
            problems = pdf_problems(data, doc.pages, doc.exact, doc.landscape) if data else ["Chrome wrote no PDF"]
            errors += [f"{doc.name}: {p}" for p in problems]
            if not problems:
                made.append((doc, data))
    if errors:
        print("PDF BUILD FAILED:\n  " + "\n  ".join(errors))
        return 1
    (out_dir / "downloads").mkdir(parents=True, exist_ok=True)
    for doc, data in made:
        (out_dir / "downloads" / doc.name).write_bytes(data)
        sizes = page_sizes(data)
        print(f"  {doc.name}: {len(sizes)} page{'s' if len(sizes) != 1 else ''} ({sum(1 for s in sizes if s == A4[::-1])} landscape), {len(data)} bytes")
    print(f"PDFs built: {len(made)} -> {out_dir / 'downloads'}")
    return 0


if __name__ == "__main__":
    sys.exit(build_pdfs(pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else build.SITE / "_out"))
