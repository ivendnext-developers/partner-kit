#!/usr/bin/env python3
"""site/build.py — builds the partner site (developer.ivendnext.com) from the kit's own Markdown.

    python3 site/build.py [OUT_DIR]        # default: site/_out

The help pages ARE the kit's guide, recipes, sample READMEs and feedback forms, converted page for page, so the site and
the kit cannot drift apart. The few pages that are not in the kit (home, get started, request a sandbox, reference apps,
feedback) are in site/pages/; they pull whole sections out of the kit's files with a line of their own:

    {{include guide/02_getting_started.md#The first call, in five steps}}     the section's text, without its heading
    {{include? guide/01_welcome.md#~Welcome}}                                  optional; "~" matches part of a heading

The needs catalogue (needs/<area>/<id>.md) is built here too, from the cards, through the loader and checker of
tools/needs/needs.py, so the tool and the site cannot disagree: one page per card, the catalogue with its A–Z list, one page
per area, door and verdict, all needs on one page, what is not possible, catalogue.json for assistants, and a "Needs this
serves" list on each recipe and sample page. A kit page pulls a generated part with a line of its own, `{{needs: possible-today}}`,
`{{needs: no-door}}` or `{{needs: popular}}`. A card that breaks a rule of needs.py fails the build. Nothing generated is
committed.

The site's one search is built here as well: search-index.json holds every card (its words, the customer's synonyms from
site/synonyms.txt, its limits and verdict) and the title, headings and first paragraphs of every guide, recipe and sample page.
site/assets-src/search.js ranks it in the browser with the vendored MiniSearch (assets/vendor/, hash-pinned by test_site.py):
a box in every page's header with instant results, and search.html (not indexed) with filters by area, door and verdict.
Without script the box opens needs/all.html, the page for the browser's own find.

Every card page ends with a What next panel written by rule from its verdict and door (NEXT_STEPS and DOOR_NEXT below: the
recipe, the sample, the sandbox, the checks and the release; or the request to file, or what to do instead) and its Related
needs. Plan a project (site/pages/plan.md, `{{plan: shortlist}}`) is a shortlist builder: site/assets-src/plan.js reads
catalogue.json, which carries each card's build step (BUILD_ORDER) and blueprint row, and keeps the shortlist in the address;
site/test_plan.mjs tests it in node. Without script the page is its seven steps.

Every sample gets a card (site/gallery.py) built from its README: `{{samples: cards}}` puts them all on a page, grouped by door,
and the samples list uses the same cards; a sample README without a run section or a door fails the build. A reference app's
card is a hand-written `{{reference-app: name | one line | doors | status | repository}}` line.

A relative link in a kit file becomes a link to the page it points at, an image is copied beside its page, and anything
else in the repository (code, a folder) becomes a link to the file on GitHub. A link to a path that does not exist fails
the build. Body, tables and code use the kit's own design tokens
(kit/design/ivn-kit.css); the frame (header, footer, home hero, headings, buttons) takes ivendnext.com's look from
site/site.css, with its font and logo copied into site/assets-src/ (every file there is copied, byte for byte, to assets/).
Needs markdown-it-py (site/requirements.txt).

What makes the site findable is site/seo.py's (its header says how): each page's title (the site name is iVendNext Developers), its
description (site/seo.json for the twenty that matter, by rule for the rest), one JSON-LD block (the Organization and site search on
the home page, a breadcrumb line the page shows and states, a TechArticle on guide, recipe, sample and card pages), one of six
preview images (site/assets-src/og/, drawn by site/og/draw.py), the sitemap's lastmod from each page's last commit (the build job
needs fetch-depth 0), llms.txt, a stub at each address in site/redirects.txt, and a 404 page with search and the A to Z list.

Site rules (CitiXsys, 2026-10-16; the ones check_links.py and test_site.py hold):
  - a script is one of our own files or comes from a host on check_links.ALLOWED_HOSTS (empty until CitiXsys adds one);
  - no inline script and no inline event handler (a data block such as application/ld+json is fine);
  - a stylesheet, font or image from another host must be on the same list; the fonts and the logo stay on our own host;
  - every page carries a content policy built from that list, so the browser enforces what the check reads.
The builders' four rules (guide chapter 3) and the rules about what a generated PDF holds (the PDF lane's) are NOT site rules;
this change does not touch them.

The branded PDFs (downloads/*.pdf) are built after this, by site/pdf/build_pdfs.py, from the same kit files; this build copies
the blueprint's template and its filled example (kit/blueprint_example.md) to downloads/ beside them. Two checks of this
build guard the blueprint pages: no two pages of one sidebar share a label, and the example's fit-gap rows carry their cards'
verdict and door.
"""
from __future__ import annotations

import html
import os
import pathlib
import posixpath
import re
import shutil
import sys

from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
sys.path.insert(0, str(ROOT / "tools" / "needs"))
import needs as catalogue  # noqa: E402  (the needs tool's own loader and checker)
import gallery  # noqa: E402  (the sample cards, read from the sample READMEs)
import check_links  # noqa: E402  (its ALLOWED_HOSTS list is also the content policy below)
import seo  # noqa: E402  (titles, descriptions, structured data, preview images, dates, llms.txt, redirects)
import devmap  # noqa: E402  (the developer's map, {{map: …}}, and the record-type pages, from the kit's own files)
REPO_URL = "https://github.com/ivendnext-developers/partner-kit"
ORG_URL = "https://github.com/ivendnext-developers"
PUBLISH_PAGE = "https://library.ivendnext.app/publish"   # the App library's Publish page: {{publish: button}}
DOMAIN = seo.DOMAIN
SEO_JSON = SITE / "seo.json"                        # the hand-written descriptions and the verification values
REDIRECTS = SITE / "redirects.txt"                  # one "old new" pair a line; the build writes a stub at each old address
IMAGE_EXT = {".png", ".gif", ".jpg", ".jpeg", ".svg", ".webp"}

NAV = [("How it works", "guide/01a_how_it_all_works.html"), ("What you can use", "map.html"), ("Needs", "needs/index.html"),
       ("Get started", "start.html"), ("Guide", "guide/index.html"), ("Recipes", "recipes/index.html"), ("Samples", "samples/index.html"),
       ("Reference apps", "reference_apps.html"), ("Publish", "publish.html"), ("Roadmap", "roadmap.html"),
       ("Feedback", "feedback.html")]
CORP = "https://www.ivendnext.com"
FOOT_CORP = [("ivendnext.com", CORP + "/"), ("Documentation", "https://docs.ivendnext.com/"), ("Application suite", CORP + "/application-suite/"), ("Partners", CORP + "/partners/"),
             ("Release 2.0", CORP + "/release/2.0/"), ("Blog", CORP + "/blog/"), ("Events", CORP + "/events/"),
             ("About us", CORP + "/about-us/"), ("Contact", CORP + "/contact/")]
FOOT_LEGAL = [("Legal", "https://legal.ivend.com/"), ("Privacy policy", "https://ivend.com/privacy-policy/")]
FOOT_COUNT = ('This site counts visits without cookies or personal data, and counts nothing if your browser says Do Not Track. '
              f'See the <a href="{FOOT_LEGAL[1][1]}">privacy policy</a>.')
GROUPS = {"guide": "Guide", "recipes": "Recipes", "samples": "Samples", "feedback": "Feedback", "needs": "Needs",
          "records": "Record types"}


# ── the page registry ──────────────────────────────────────────────────────────────────────────────────────────────
class Page:
    def __init__(self, src: str, out: str, group: str = ""):
        self.src, self.out, self.group = src, out, group
        self.text = (ROOT / src).read_text("utf-8")
        m = re.search(r"^# (.+)$", self.text, re.M)
        self.title = re.sub(r"[`*]", "", m.group(1)).strip() if m else out
        self.html = ""
        self.toc: list[tuple[str, str]] = []

    @property
    def short(self) -> str:                      # the nav label: a chapter's number and name; a sample keeps its whole title
        return self.title if self.group == "samples" else self.title.split(" — ")[0].strip()


EXAMPLE = "kit/blueprint_example.md"                # the blueprint filled in for an invented retailer


def collect() -> list[Page]:
    pages = [Page("site/pages/" + p.name, "index.html" if p.stem == "index" else p.stem + ".html")
             for p in sorted((SITE / "pages").glob("*.md"))]
    for folder in ("guide", "recipes", "feedback"):
        for p in sorted((ROOT / folder).glob("*.md")):
            index = folder != "recipes" and p.name == "README.md"
            pages.append(Page(f"{folder}/{p.name}", f"{folder}/{'index' if index else p.stem}.html", folder))
    pages.append(Page("kit/blueprint.md", "kit/blueprint.html", "guide"))
    pages.append(Page(EXAMPLE, "kit/blueprint_example.html", "guide"))                        # also a download, below
    pages.append(Page("kit/blueprint_template.md", "kit/blueprint_template.html", "guide"))   # also a download, below
    for p in sorted((ROOT / "samples").glob("*/README.md"), key=lambda p: int(re.sub(r"\D", "", p.parent.name.split("_")[0]))):
        pages.append(Page(f"samples/{p.parent.name}/README.md", f"samples/{p.parent.name}/index.html", "samples"))
    return pages


def label_errors(pages: list[Page]) -> list[str]:
    """Two pages of one sidebar with the same label: a visitor cannot tell them apart (the needs sidebar lists its areas)."""
    seen: dict = {}
    bad = []
    for p in pages:
        if not p.group or p.group == "needs" or p.out == f"{p.group}/index.html":
            continue
        if (p.group, p.short) in seen:
            bad.append(f"{p.src}: its sidebar label {p.short!r} is also {seen[p.group, p.short]}'s; give one a title of its own")
        seen.setdefault((p.group, p.short), p.src)
    return bad


def example_errors(cards: list) -> list[str]:
    """The blueprint example's fit-gap held to today's cards: a row that names a card carries that card's verdict word and
    door, so a card that changes fails the build instead of quietly aging the example. A row with no card says "none"."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in section(EXAMPLE, "(b) Fit-gap").splitlines()
            if ln.startswith("|") and not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+\s*", ln)]
    if not rows or not {"Card", "Status", "Door"} <= set(rows[0]):
        return [f"{EXAMPLE}: no (b) Fit-gap table with Card, Status and Door columns"]
    ci, si, di = (rows[0].index(h) for h in ("Card", "Status", "Door"))
    by_id, bad = {c.id: c for c in cards}, []
    for r in rows[1:]:
        where = f"{EXAMPLE} (b) row {r[0]}"
        if len(r) != len(rows[0]):
            bad.append(f"{where}: {len(r)} cells, not {len(rows[0])}")
            continue
        if r[si] not in catalogue.STATUSES.values():
            bad.append(f"{where}: Status {r[si]!r} is not one of the four verdicts")
        if r[ci] == "none":
            continue
        c = by_id.get(r[ci])
        if not c:
            bad.append(f"{where}: no card has the id {r[ci]!r} (write a card id, or none)")
            continue
        if r[si] != catalogue.STATUSES[c.status]:
            bad.append(f"{where}: Status {r[si]!r}, but the card {c.id} now says {catalogue.STATUSES[c.status]!r}: update the row")
        if door_name(c.door).lower() not in r[di].lower():
            bad.append(f"{where}: Door {r[di]!r} does not name the card {c.id}'s door, {door_name(c.door)!r}")
    return bad


# ── links ──────────────────────────────────────────────────────────────────────────────────────────────────────────
class Ctx:
    """What a piece of Markdown needs to turn its links into site links: where it was written and where it lands."""
    def __init__(self, registry: dict, out_dir: pathlib.Path, errors: list, assets: set):
        self.registry, self.out_dir, self.errors, self.assets = registry, out_dir, errors, assets
        self.src = self.out = ""
        self.cards: list = []                    # the needs cards, for a {{needs: …}} line
        self.samples: list = []                  # the sample cards, for {{samples: cards}}
        self.door_pages: set = set()             # the doors that have a needs page

    def url(self, url: str) -> str:
        if url.startswith("site:"):              # a page the build makes (the catalogue's lists), by its place in the site
            return posixpath.relpath(url[5:].partition("#")[0], posixpath.dirname(self.out) or ".") + (
                "#" + url.partition("#")[2] if "#" in url else "")
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("#") or not url:
            return url
        path, _, frag = url.partition("#")
        base = posixpath.dirname(self.src)
        rel = posixpath.normpath(posixpath.join(base, path.split("?")[0]))
        if rel.startswith("..") or not (ROOT / rel).exists():
            self.errors.append(f"{self.src}: link to a path that does not exist: {url}")
            return url
        here = posixpath.dirname(self.out) or "."
        if rel in self.registry:
            target = posixpath.relpath(self.registry[rel].out, here)
        elif pathlib.PurePosixPath(rel).suffix.lower() in IMAGE_EXT:
            self.assets.add(rel)
            target = posixpath.relpath(rel, here)
        else:
            kind = "tree" if (ROOT / rel).is_dir() else "blob"
            return f"{REPO_URL}/{kind}/main/{rel}" + ("#" + frag if frag else "")
        return target + ("#" + frag if frag else "")


def slug(text: str) -> str:                     # GitHub's heading anchors, so links written for GitHub still land
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def section(src: str, heading: str) -> str:
    """The text under a heading (without it) up to the next heading of the same or a higher level."""
    want = heading.removeprefix("~").lower()
    lines, out, level, fence = (ROOT / src).read_text("utf-8").split("\n"), [], 0, False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,6}) (.+?)\s*$", ln)
        if level and m and len(m.group(1)) <= level:
            break
        if level:
            out.append(ln)
        elif m and ((want in m.group(2).lower()) if heading.startswith("~") else (m.group(2) == heading)):
            level = len(m.group(1))
    return "\n".join(out).strip() if level else ""


# ── rendering ──────────────────────────────────────────────────────────────────────────────────────────────────────
MD = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")


def render(text: str, ctx: Ctx, seen: dict, toc: list | None, depth: int = 0) -> str:
    """Markdown to HTML for a piece written in ctx.src and landing in ctx.out."""
    includes: dict[str, str] = {}

    def include(m: re.Match) -> str:
        optional, spec = bool(m.group(1)), m.group(2)
        src, _, head = spec.partition("#")
        body = section(src, head)
        if not body:
            if not optional:
                ctx.errors.append(f"{ctx.src}: include finds no section {spec}")
            elif os.environ.get("SITE_REQUIRE_OPTIONAL") == "true":      # a deploy run: nothing optional may be missing
                ctx.errors.append(f"{ctx.src}: optional include {spec} is missing, and this is a deploy build")
            else:
                print(f"  optional include not found (skipped): {spec}")
            return ""
        saved = (ctx.src, ctx.out)
        ctx.src = src
        try:
            includes[f"@@INCLUDE{len(includes)}@@"] = render(body, ctx, seen, None, depth + 1)
        finally:
            ctx.src, ctx.out = saved
        return f"\n\n@@INCLUDE{len(includes) - 1}@@\n\n"

    text = re.sub(r"^\{\{include(\??) (.+?)\}\}\s*$", include, text, flags=re.M)
    text = re.sub(r"^\{\{needs: ([a-z-]+)\}\}\s*$", lambda m: generated(m.group(1), ctx), text, flags=re.M)
    text = re.sub(r"^\{\{api: reference\}\}\s*$", lambda m: api_reference(ctx), text, flags=re.M)
    text = re.sub(r"^\{\{map: (calls|points|manifest|screens)\}\}\s*$", lambda m: map_part(m.group(1), ctx), text, flags=re.M)

    def raw(piece: str) -> str:                  # a piece of HTML the build wrote, set in after the Markdown is rendered
        includes[f"@@INCLUDE{len(includes)}@@"] = piece
        return f"\n\n@@INCLUDE{len(includes) - 1}@@\n\n"

    here = posixpath.dirname(ctx.out)
    text = re.sub(r"^\{\{plan: shortlist\}\}\s*$", lambda m: raw(plan_tool(here)), text, flags=re.M)
    text = re.sub(r"^\{\{hosting: order\}\}\s*$", lambda m: raw(hosting_tool(here)), text, flags=re.M)
    text = re.sub(r"^\{\{publish: button\}\}\s*$", lambda m: raw(  # the App library's Publish page (PUBLISHWEB)
        f'<p class="hero-cta"><a class="site-btn" href="{PUBLISH_PAGE}">Publish</a></p>'), text, flags=re.M)
    text = re.sub(r"^\{\{samples: cards\}\}\s*$", lambda m: raw(gallery.grouped(
        ctx.samples, here, REPO_URL, catalogue.DOORS, ctx.door_pages, slug)), text, flags=re.M)
    text = re.sub(r"(?:^\{\{reference-app: .+\}\}\s*$\n?)+", lambda m: raw('<ul class="cards">' + "".join(
        gallery.reference_app(spec, ORG_URL, catalogue.DOORS, ctx.errors, ctx.src, NOT_OPEN_YET) for spec in re.findall(r"\{\{reference-app: (.+)\}\}", m.group()))
        + "</ul>"), text, flags=re.M)
    tokens = MD.parse(text)
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            inline = tokens[i + 1]
            label = "".join(c.content for c in inline.children if c.type in ("text", "code_inline"))
            sid = slug(label)
            n = seen.get(sid, 0)
            seen[sid] = n + 1
            t.attrSet("id", sid if n == 0 else f"{sid}-{n}")
            if toc is not None and t.tag == "h2":
                toc.append((t.attrGet("id"), label))
        for c in (t.children or []):
            if c.type == "link_open":
                c.attrSet("href", ctx.url(c.attrGet("href")))
            elif c.type == "image":
                written = c.attrGet("src")
                c.attrSet("src", ctx.url(written))
                c.attrSet("loading", "lazy")
                size = seo.image_size(ROOT / posixpath.normpath(posixpath.join(posixpath.dirname(ctx.src), written.split("#")[0])))
                if size:                              # room reserved before the file arrives, so the page does not jump
                    c.attrSet("width", str(size[0]))
                    c.attrSet("height", str(size[1]))
    out = MD.renderer.render(tokens, MD.options, {})
    out = out.replace("<table>", '<div class="tw" tabindex="0" role="region" aria-label="Table"><table>').replace("</table>", "</table></div>")
    out = out.replace("<pre>", '<pre tabindex="0">')
    for key, val in includes.items():
        out = out.replace(f"<p>{key}</p>", val)
    return out


def first_use(page: Page) -> str:                # a sample's card text: its "When to use it" line, else its first paragraph
    m = re.search(r"^\*\*When to use it:?\*\*:?\s*(.+)$", page.text, re.M)
    if not m:
        paras = [p for p in page.text.split("\n\n")[1:] if p.strip() and not p.lstrip().startswith(("!", "*", "#", "|", "-", "`"))]
        m = re.match(r"(.+)", paras[0].replace("\n", " ")) if paras else None
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m.group(1)) if m else ""
    return re.sub(r"[`*]", "", text).strip()


def describe(text: str, fallback: str) -> str:
    """A page's meta description: its first plain paragraph after the title, about 155 characters, no Markdown."""
    for para in text.split("\n\n")[1:]:
        p = para.strip()
        if p and not p.startswith(("!", "*", "#", "|", "-", "`", ">", "{", "1.", "[")):
            p = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", p.replace("\n", " "))
            p = re.sub(r"[`*_]", "", p).strip()
            if len(p) > 155:
                p = p[:155].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
            return p
    return fallback


canonical = seo.canonical                         # one address per page: a folder's index is its folder


# ── the shell ──────────────────────────────────────────────────────────────────────────────────────────────────────
def up_of(out: str) -> str:                       # the way back to the site's root from a page: "", "../", "../../"
    return "../" * out.count("/")


def hero_of(body: str) -> tuple[str, str]:
    """The home page's hero: its title, first paragraph and line of links, lifted out of the body into a full-width band.
    The words are the page's own; the links become buttons, the first one primary."""
    m = re.match(r"\s*(<h1[^>]*>.*?</h1>)\s*(<p>.*?</p>)\s*<p>((?:\s*(?:·\s*)?<a href=\"[^\"]+\">[^<]+</a>)+)\s*</p>", body, re.S)
    if not m:
        return "", body
    links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', m.group(3))
    buttons = "".join(f'<a class="site-btn{" site-btn-ghost" if i else ""}" href="{h}">{t}</a>' for i, (h, t) in enumerate(links))
    lede = m.group(2).replace("<p>", '<p class="lede">', 1)
    return (f'<section class="hero"><div class="hero-in"><p class="eyebrow">Partner kit</p>{m.group(1)}{lede}'
            f'<p class="hero-cta">{buttons}</p></div></section>'), body[m.end():]


def content_policy() -> str:
    """The Content-Security-Policy every page carries, built from check_links.ALLOWED_HOSTS (read at each call). A meta tag
    cannot send frame-ancestors or report-uri. The site's two forms (the header's search box and search.html) submit to
    the site itself, which form-action 'self' allows."""
    hosts = "".join(" https://" + h for h in check_links.ALLOWED_HOSTS)
    return "; ".join(["default-src 'self'", "script-src 'self'" + hosts, "connect-src 'self'" + hosts,
                      "img-src 'self' data:" + hosts, "font-src 'self'" + hosts, "style-src 'self' 'unsafe-inline'" + hosts,
                      "object-src 'none'", "base-uri 'self'", "form-action 'self'"])


def analytics_meta() -> str:
    """The page's one named counter, from the one constant (check_links.ANALYTICS_HOST). The content policy is built from the
    same list, so a counter the list does not hold is refused here and by the browser."""
    if check_links.ANALYTICS_HOST not in check_links.ALLOWED_HOSTS:
        raise ValueError(f"check_links.ANALYTICS_HOST ({check_links.ANALYTICS_HOST}) is not on ALLOWED_HOSTS: the content policy would block it")
    return f'<meta name="ivn-analytics" content="https://{check_links.ANALYTICS_HOST}">'


def search_box(up: str) -> str:
    """The header's search box. With script, search.js turns it into instant results and sends Enter to search.html; without
    script the form opens needs/all.html, every card on one page for the browser's own find."""
    return (f'<form class="site-search" role="search" action="{up}needs/all.html" method="get" data-root="{up}">'
            f'<label class="vh" for="q-top">Search the site</label>'
            f'<input id="q-top" name="q" type="search" placeholder="Search the site" autocomplete="off" role="combobox" '
            f'spellcheck="false" aria-autocomplete="list" aria-expanded="false" aria-controls="q-top-list">'
            f'<ul id="q-top-list" class="search-pop" role="listbox" aria-label="Results" hidden></ul></form>')


def shell(page_title: str, body: str, out: str, *, side: str = "", toc: list | None = None, foot: str = "",
          absolute: bool = False, sha: str = "", desc: str = "", noindex: bool = False, hero: str = "",
          meta: "seo.PageMeta | None" = None, crumbs: str = "", verify: dict | None = None) -> str:
    up = "/" if absolute else up_of(out)
    own = out in OWN_POLICY
    nav = "".join(f'<li><a href="{up}{href}"{" aria-current=\"page\"" if href == out else ""}>{html.escape(label)}</a></li>'
                  for label, href in NAV)
    li = lambda items: "".join(f'<li><a href="{h}">{html.escape(t)}</a></li>' for t, h in items)
    foot_site = li([("Needs catalogue", up + "needs/index.html"), ("Plan a project", up + "plan.html"),
                    ("Get started", up + "start.html"), ("Guide", up + "guide/index.html"), ("Recipes", up + "recipes/index.html"),
                    ("Samples", up + "samples/index.html"), ("Reference apps", up + "reference_apps.html"),
                    ("Request a sandbox", up + "sandbox.html"), ("Publish your app", up + "publish.html"),
                    ("App library", seo.LIBRARY), ("App library: for partners", seo.LIBRARY + "/build")])
    foot_kit = li([("The kit on GitHub", REPO_URL), ("Possible, not possible", up + "guide/16_possible_not_possible.html"),
                   ("Tell us what is missing", up + "feedback.html")])
    desc = desc or "The iVendNext Developers site: the guide, recipes and samples for anyone who builds for an iVendNext customer."
    full_title = seo.title_of(meta.name, meta.home) if meta else seo.title_of(page_title)
    if not noindex and not meta:
        raise ValueError(f"{out}: an indexable page needs its PageMeta (seo.PageMeta); without one it would drop out of search")
    if noindex:
        head_meta = f'<meta name="robots" content="noindex">\n<meta name="description" content="{html.escape(desc, quote=True)}">'
    else:
        head_meta = seo.head_tags(meta, out, full_title, verify)
    on_page = ""
    if toc and len(toc) > 1:
        on_page = ('<nav class="toc" aria-label="On this page"><h2>On this page</h2><ul>'
                   + "".join(f'<li><a href="#{i}">{html.escape(t)}</a></li>' for i, t in toc) + "</ul></nav>")
    return f"""<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{page_policy() if own else content_policy()}">
{'<meta name="referrer" content="no-referrer">' if own else analytics_meta()}
<title>{html.escape(full_title)}</title>
{head_meta}
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}assets/ivn-kit.css">
<link rel="stylesheet" href="{up}assets/site.css">
{"" if own else f'''<script src="{up}assets/analytics.js" defer></script>
<script src="{up}assets/search.js" defer></script>'''}
</head>
<body class="ivn">
<a class="skip" href="#main">Skip to the content</a>
<header class="top">
<div class="band"><div class="band-in"><a href="{CORP}/">ivendnext.com</a><a href="{CORP}/partners/">Partners</a></div></div>
<div class="bar">
<a class="brand" href="{up}index.html"{" aria-current=\"page\"" if out == "index.html" else ""}><img src="{up}assets/logo.svg" alt="iVendNext" width="132" height="24"><span class="brand-sub">Developers</span></a>
{search_box(up)}
<nav class="nav-wide" aria-label="Main"><ul>{nav}</ul></nav>
<a class="site-btn cta" href="{up}sandbox.html">Request a sandbox</a>
<details class="menu"><summary>Menu</summary><nav aria-label="Main"><ul>{nav}<li><a href="{up}sandbox.html">Request a sandbox</a></li></ul></nav></details>
</div>
</header>
{(f'<main id="main" class="home">{hero}<div class="wrap"><div class="content">{body}{foot}</div>{on_page}</div></main>') if hero else
 (f'<div class="wrap{" has-side" if side else ""}">{side}<main id="main">{crumbs}{body}{foot}</main>{on_page}</div>')}
<footer class="bottom">
<div class="foot-in">
<div class="foot-brand"><img src="{up}assets/logo-on-dark.svg" alt="iVendNext" width="132" height="24">
<p>This site is built from the iVendNext partner kit's own guide{(" · build " + sha) if sha else ""}.</p></div>
<nav aria-label="This site"><h2>Build</h2><ul>{foot_site}</ul></nav>
<nav aria-label="The kit"><h2>The kit</h2><ul>{foot_kit}</ul></nav>
<nav aria-label="iVendNext"><h2>iVendNext</h2><ul>{li(FOOT_CORP)}</ul></nav>
</div>
<div class="foot-base"><ul>{li(FOOT_LEGAL)}</ul>
<p class="foot-note">{FOOT_COUNT}</p></div>
</footer>
</body>
</html>
"""


class ListPage:                                   # a generated list page (recipes, samples): the sidebar needs its place only
    def __init__(self, out: str, group: str):
        self.out, self.group, self.src = out, group, ""


def sidebar(page, pages: list[Page], lists: list[ListPage], up: str) -> str:
    if not page.group:
        return ""
    if page.group == "needs":                    # the catalogue's sidebar: its areas, not its 80-odd cards
        cur = lambda out: ' aria-current="page"' if out == page.out else ""
        li = [f'<li><a href="{up}needs/index.html"{cur("needs/index.html")}><strong>Needs: all</strong></a></li>']
        li += [f'<li><a href="{up}needs/{a}/index.html"{cur(f"needs/{a}/index.html")}>{html.escape(name)}</a></li>'
               for a, name in catalogue.AREAS.items()]
        li += [f'<li><a href="{up}needs/not-possible.html"{cur("needs/not-possible.html")}>What is not possible</a></li>']
        return f'<nav class="side" aria-label="Needs"><ul>{"".join(li)}</ul></nav>'
    if page.group == "records":                  # the record types' sidebar: the index, then each record type A to Z
        cur = lambda out: ' aria-current="page"' if out == page.out else ""
        recs = sorted(devmap.record_index()["records"], key=lambda r: r["name"].lower())
        li = [f'<li><a href="{up}records/index.html"{cur("records/index.html")}><strong>Record types: all</strong></a></li>']
        for r in recs:
            out = f"records/{r['slug']}.html"
            li.append(f'<li><a href="{up}{out}"{cur(out)}>{html.escape(r["name"])}</a></li>')
        return f'<nav class="side" aria-label="Record types"><ul>{"".join(li)}</ul></nav>'
    idx = f"{page.group}/index.html"
    items = [p for p in pages if p.group == page.group and p.out != idx]
    cur = lambda out: ' aria-current="page"' if out == page.out else ""
    li = [f'<li><a href="{up}{idx}"{cur(idx)}><strong>{GROUPS[page.group]}: all</strong></a></li>']
    li += [f'<li><a href="{up}{p.out}"{cur(p.out)}>{html.escape(p.short)}</a></li>' for p in items]
    return f'<nav class="side" aria-label="{GROUPS[page.group]}"><ul>{"".join(li)}</ul></nav>'


def prev_next(page: Page, pages: list[Page], up: str) -> str:
    if page.group != "guide" or not page.out.startswith("guide/") or page.out.endswith("index.html"):
        return ""
    seq = [p for p in pages if p.out.startswith("guide/") and not p.out.endswith("index.html")]
    i = seq.index(page)
    a = f'<a rel="prev" href="{up}{seq[i-1].out}">Previous: {html.escape(seq[i-1].short)}</a>' if i else "<span></span>"
    b = f'<a rel="next" href="{up}{seq[i+1].out}">Next: {html.escape(seq[i+1].short)}</a>' if i + 1 < len(seq) else "<span></span>"
    return f'<nav class="pn" aria-label="Chapters">{a}{b}</nav>'



# ── the needs catalogue ───────────────────────────────────────────────────────────────────────────────────────────
# Where the guide explains each door: a card's door links its facet page, and the facet page links this.
DOOR_HOW = {"configure": "guide/04_configure_first.md", "outside-app": "guide/05_outside_apps_and_event_feed.md",
            "event-feed": "guide/05_outside_apps_and_event_feed.md", "till-key": "guide/06_till_keys.md",
            "manifest": "guide/07_manifests.md", "sandboxed-function": "guide/08_sandboxed_functions.md",
            "our-connector": "guide/10_integrations.md", "payment-connector": "guide/11_payments_fiscal_hardware.md",
            "wallet": "guide/11_payments_fiscal_hardware.md", "fiscal-reader": "guide/11_payments_fiscal_hardware.md",
            "desk-action": "guide/13a_screens_and_ux.md", "partner-page": "guide/13a_screens_and_ux.md",
            "none": "guide/03_ladder_and_never_list.md"}           # every other door is an extension point: chapter 9
FIRST_RUNGS = {"configure", "outside-app", "our-connector"}      # chapter 16's first table; the rest is its second


class GenPage:
    """A page the build writes from the cards. `src` is where its Markdown is taken to be written (links resolve from there)."""
    def __init__(self, src: str, out: str, title: str, text: str, desc: str, group: str = "needs"):
        self.src, self.out, self.title, self.text, self.desc, self.group = src, out, title, text, desc, group
        self.html, self.toc = "", []


def rel(target: str, src: str) -> str:            # a link to a kit file, written from `src`
    return posixpath.relpath(target, posixpath.dirname(src) or ".")


def need_link(c, src: str) -> str:
    return f"[{c.asks}]({rel(c.rel, src)})"


def topic_name(c) -> str:
    return catalogue.TOPICS.get(c.area, {}).get(c.topic, c.topic)


def newest(cards: list, n: int = 12) -> list:
    """The cards checked most recently (their `verified` date), newest first: the catalogue's New and changed list."""
    dated = [c for c in cards if c.checked_on()]
    return sorted(dated, key=lambda c: (-c.checked_on().toordinal(), az_key(c)))[:n]


def door_name(door: str) -> str:
    return catalogue.DOORS.get(door, door)


def need_table(cards: list, src: str) -> str:
    rows = "".join(f"| {need_link(c, src)} | {c.verdict} | [{door_name(c.door)}](site:needs/door/{c.door}.html) |\n" for c in cards)
    return "| The customer asks | Verdict | Door |\n|---|---|---|\n" + rows


def az_key(c) -> str:                             # the customer's words, a leading "a", "an" or "the" set aside
    return re.sub(r"^(a|an|the) ", "", c.asks.lower())


def by_asks(cards: list) -> list:
    return sorted(cards, key=az_key)


def generated(kind: str, ctx: "Ctx") -> str:
    """The Markdown a {{needs: …}} line in a kit page stands for, with links written from that page."""
    cards = by_asks(ctx.cards)
    open_ = [c for c in cards if c.status in ("ready", "ready-with-limits")]
    if kind == "possible-today":
        return ("### With configuration, our connectors and outside apps\n\n" + need_table([c for c in open_ if c.door in FIRST_RUNGS], ctx.src)
                + "\n### With an extension point or a manifest\n\n" + need_table([c for c in open_ if c.door not in FIRST_RUNGS], ctx.src))
    if kind == "no-door":
        rows = ""
        for c in cards:
            if c.status in ("not-yet", "not-possible"):
                todo = " ".join(l.replace("**", "") for l in c.limits)
                ask = f"Ask for {', '.join(c.requests)}." if c.blocked_by == "extension-point" else ""
                rows += f"| {need_link(c, ctx.src)} | {c.verdict} | {' '.join(x for x in (todo, ask) if x)} |\n"
        return "| The customer asks | Verdict | Instead, today, and what to ask for |\n|---|---|---|\n" + rows
    if kind == "popular":
        return popular(cards, ctx.src)
    ctx.errors.append(f"{ctx.src}: unknown generated part {{{{needs: {kind}}}}}")
    return ""


# ── the API reference: the Markdown `{{api: reference}}` stands for, written from the kit's API description ─────────────
API_SPEC = "api/openapi.yaml"
API_METHODS = ("get", "post", "put", "patch", "delete")


def api_reference(ctx: "Ctx", spec_path: str = API_SPEC) -> str:
    """One section per path of the API description: each method with its purpose, parameters, body, sign-in header and
    answers. A path with no method, a method with no summary, or a $ref that names nothing fails the build."""
    import yaml                                   # site/requirements.txt; only this page reads YAML
    spec = yaml.safe_load((ROOT / spec_path).read_text("utf-8"))
    comps = spec.get("components") or {}

    def deref(x):
        ref = x.get("$ref") if isinstance(x, dict) else None
        if not ref:
            return x, ""
        node = spec
        for part in ref.removeprefix("#/").split("/"):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            ctx.errors.append(f"{spec_path}: {ref} names nothing")
            return {}, ""
        return node, ref.rsplit("/", 1)[1]

    def cell(s) -> str:
        return " ".join(str(s or "").split()).replace("|", "\\|")

    def signin(op: dict, where: str) -> str:
        reqs = op["security"] if "security" in op else spec.get("security") or []    # any one requirement; all of its names
        if not any(reqs):
            return "**Sign-in:** none."
        options = []
        for req in reqs:
            parts = []
            for n in req:
                s = (comps.get("securitySchemes") or {}).get(n)
                if not s:
                    ctx.errors.append(f"{spec_path}: {where} signs in with {n}, which components.securitySchemes does not hold")
                    continue
                parts.append(f"the `{s.get('name')}` {s.get('in')}" + (f": {cell(s['description'])}" if s.get("description") else ""))
            options.append(" and ".join(parts))
        return "**Sign-in:** " + " Or ".join(o for o in options if o)

    out = []
    for path, ops in (spec.get("paths") or {}).items():
        ops = deref(ops or {})[0]
        methods = [m for m in API_METHODS if m in (ops or {})]
        if not methods:
            ctx.errors.append(f"{spec_path}: {path} has no method")
            continue
        out.append(f"## `{path}`\n")
        for m in methods:
            op, where = ops[m], f"{m.upper()} {path}"
            if not op.get("summary"):
                ctx.errors.append(f"{spec_path}: {where} has no summary")
            out.append(f"### `{m.upper()}` {cell(op.get('summary'))}\n")
            if op.get("description"):
                out.append(cell(op["description"]) + "\n")
            params = [deref(p)[0] for p in [*(ops.get("parameters") or []), *(op.get("parameters") or [])]]
            if params:
                out.append("| Parameter | In | Required | What it is |\n|---|---|---|---|")
                for p in params:
                    what = p.get("description") or (f"For example `{p['example']}`." if "example" in p else "")
                    out.append(f"| `{p.get('name')}` | {p.get('in')} | {'yes' if p.get('required') else 'no'} | {cell(what)} |")
                out.append("")
            body = (deref(op.get("requestBody") or {})[0]).get("content", {}).get("application/json", {}).get("schema")
            if body is not None:
                schema, name = deref(body)
                need = ", ".join(f"`{f}`" for f in schema.get("required") or [])
                out.append(f"**Body:** a JSON object" + (f" (`{name}`)" if name else "")
                           + (f", with {need} required." if need else ", with the record's fields.") + "\n")
            out.append(signin(op, where) + "\n")
            answers: dict[str, list[str]] = {}                  # one line per meaning: "`401`, `403` An error. …"
            for code, r in (op.get("responses") or {}).items():
                answers.setdefault(cell(deref(r)[0].get("description")), []).append(f"`{code}`")
            out.append("**Answers:** " + " · ".join(f"{', '.join(c)} {t}" for t, c in answers.items()) + "\n")
    return "\n".join(out)


# ── the developer's map: the Markdown each `{{map: …}}` line stands for (site/devmap.py writes it from its source) ──────
def map_part(kind: str, ctx: "Ctx") -> str:
    if kind == "calls":
        return devmap.calls({r["slug"] for r in devmap.record_index()["records"]}, ctx.src)
    return {"points": devmap.points, "manifest": devmap.manifest}[kind](ctx.src) if kind != "screens" else devmap.screens(ctx.src)


# ── what next: the steps under every card, written by rule from its verdict and door ──────────────────────────────────
# Data, not branches: a card's panel is NEXT_STEPS[its status] (a not-yet card: by what blocks it), each step's words from
# step_lines() below, then DOOR_NEXT's line for its door if there is one. Every link is to a page of this site (the build and
# the link check hold them), except the request form, which lives in a private repository: test_site.py holds that address
# equal to the one on the feedback page.
POINT_FORM = "https://github.com/ivendnext-developers/partner-feedback/issues/new?template=2_point_request.yml"
# The words beside every link to a private repository of the org. MEMBERS_ONLY: the request form (partner-feedback, which
# onboarded members can read), on the needs pages and, through catalogue.json, on Plan a project. NOT_OPEN_YET: the reference
# apps (gallery.py), whose repositories only the kit's maintainers can open. Both carry "page not found", the clause
# check_links.py looks for on a page that links a private repository.
MEMBERS_ONLY = ("members only: the form is in a private repository on GitHub, so anyone not signed in as an onboarded member "
                "sees GitHub's \"page not found\"")
NOT_OPEN_YET = ("not open yet: the repository is private to the kit's maintainers, so anyone else, members included, sees "
                "GitHub's \"page not found\"")
NEXT_STEPS = {"ready": ("recipe", "sample", "sandbox", "checks", "release", "more"),
              "ready-with-limits": ("tell", "recipe", "sample", "sandbox", "checks", "release", "more"),
              "not-yet/extension-point": ("ask", "until"),
              "not-yet/product-work": ("ask-us", "until"),
              "not-possible": ("instead",)}
NO_CODE = {"configure", "receipt", "our-connector"}           # nothing to code: checked and released as settings, not as an app
NO_CODE_STEPS = {"checks": "check-settings", "release": "release-settings"}
DOOR_NEXT = {
    "configure": "Nothing to code: write down each setting you make on your sandbox, so it is made the same way on the customer's site.",
    "receipt": "Nothing to code: write down each receipt setting, so it is made the same way on the customer's site.",
    "our-connector": "Nothing to code on our side of it: set up our connector on your sandbox, then write down each setting.",
    "outside-app": "Stop your service for a while and start it again: it must catch up from the event feed, missing nothing.",
    "event-feed": "Stop your service for a while and start it again: it must catch up from the event feed, missing nothing.",
    "till-key": "Test it with your service answering, and again with it stopped: the till must say so in words, never wait.",
    "check-before-payment": "Test it with your service stopped: the till applies the answer you declared for when it is down.",
    "capture-on-event": "Test it with your service stopped: the till applies the answer you declared for when it is down.",
    "fulfil-at-sale": "Test it with your service stopped: the sale stands, the receipt waits, and a refund of the line waits for the cancel.",
    "manifest": "Install it on your sandbox the way the shop's administrator will; the checker refuses a manifest that declares code.",
    "payer": "Test it with your service stopped: the cashier reads that the payer cannot be reached, and the customer pays it all or the sale is held.",
    "register-books": "Install the books on your sandbox, then submit a stock document of an item a book takes: one line per book, numbered, never edited.",
    "open-check": "Send every write twice with the same key: it is written once. Send that key again with other lines: it is refused.",
    "station-ticket": "Move one ticket the same step twice: the second answers already. Then stop the live connection: your screen must read the whole board again every few seconds.",
    "sandboxed-function": "Run it on the till offline as well as online: it must give the same answer.",
}
# The order a shortlist is built in (Plan a project): the ladder's order (guide chapter 3), with one change: your own
# records (a manifest) come straight after configuration, because the services and screens built after them read and
# write those records. Every door is in exactly one step (build() refuses a door that is not).
EXTENSION_DOORS = {"check-before-payment", "document-check", "capture-on-event", "field-rules", "save-rules", "desk-action",
                   "partner-page", "scan-source", "label-layout", "wallet", "fiscal-reader", "payment-connector",
                   "fulfil-at-sale", "payer", "register-books", "open-check",
                   "station-ticket"}
BUILD_ORDER = [
    ({"configure", "receipt"}, "Configure first: the settings in iVendNext Desk that everything after them relies on."),
    ({"manifest"}, "Then your own records and fields: the services and screens built after them read and write them."),
    ({"our-connector", "outside-app", "event-feed"}, "Then the connectors and outside apps: they run on a server and keep the records filled."),
    ({"till-key"}, "Then the till keys: the cashier's buttons, which call a service that is already running."),
    (EXTENSION_DOORS, "Then the extension points: your service answers the till or Desk at a published moment."),
    ({"sandboxed-function"}, "Then the sandboxed function, last of the code: the rules it applies are settled by then."),
    ({"request"}, "Not yet: ask now (the extension-point request, or our product work), so it is in the queue; build it when it ships."),
    ({"none"}, "Not possible: do what the card says instead."),
]


def build_step(door: str) -> int:                  # an unknown door sorts last; needs.py check has already failed the build
    return next((i for i, (doors, _) in enumerate(BUILD_ORDER) if door in doors), len(BUILD_ORDER))


def build_why(door: str) -> str:
    i = build_step(door)
    return BUILD_ORDER[i][1] if i < len(BUILD_ORDER) else ""


def order_errors() -> list[str]:
    bad = [f"site/build.py BUILD_ORDER: door {d} is in no step, or in more than one"
           for d in catalogue.DOORS if sum(d in doors for doors, _ in BUILD_ORDER) != 1]
    return bad + [f"site/build.py BUILD_ORDER: {d} is not a door" for doors, _ in BUILD_ORDER for d in doors if d not in catalogue.DOORS]


def request_url(handle: str, c) -> str:            # the request form, its title prefilled with the handle and the need
    from urllib.parse import quote
    return POINT_FORM + "&title=" + quote(f"Extension-point request: {handle} — {c.asks}", safe="")


def unbold(line: str) -> str:
    return line.replace("**", "")


NAMED_CARD = re.compile(r"the card \*([a-z0-9-]+)\*")       # how a limit line names another card
TODAY = re.compile(r"^Today\b[,:]?\s*")                       # a limit line that says what to do meanwhile


def proof_title(p: str, titles: dict) -> str:       # a recipe's or sample's title; a kit file not on the site, its own heading
    key, f = p.rstrip("/"), ROOT / p.rstrip("/")
    return titles.get(key) or (Page(key, "", "").title if f.suffix == ".md" and f.is_file() else key)


def proof_label(paths: list[str]) -> str:          # what the step calls it: a recipe, a guide chapter, or a page of the kit
    if all(p.startswith("recipes/") for p in paths):
        return "Follow the recipe"
    return "Read the chapter" if all(p.startswith("guide/") for p in paths) else "Start from"


def step_lines(c, titles: dict, src: str, by_id: dict | None = None) -> list[str]:
    """The numbered steps of a card's What next panel, as Markdown with links written from the card's file. A card named in a
    limit line (*the card <id>*) becomes a link to it."""
    by_id = by_id or {}
    link = lambda p: f"[{proof_title(p, titles)}]({rel(p, src)})"
    named = lambda s: NAMED_CARD.sub(lambda m: f"the card [{by_id[m.group(1)].asks}]({rel(by_id[m.group(1)].rel, src)})"
                                     if m.group(1) in by_id else m.group(), s)
    how = DOOR_HOW.get(c.door, "guide/09_points_and_requests.md")
    today = [l for l in c.limits if TODAY.match(unbold(l))]
    words = {
        "tell": lambda: [f"**Tell the customer** the {len(c.limits)} limit{'s' if len(c.limits) > 1 else ''} above, and write "
                         f"{'them' if len(c.limits) > 1 else 'it'} into the proposal."],
        "recipe": lambda: [f"**{proof_label(c.paths('recipe'))}:** {' · '.join(link(p) for p in c.paths('recipe'))}." if c.paths("recipe")
                           else f"**Read how the door works:** {link(how)}."],
        "sample": lambda: [f"**Copy the sample:** {' · '.join(link(p) for p in c.paths('sample'))}, and change it."] if c.paths("sample") else [],
        "sandbox": lambda: [f"**Build and test it on your sandbox** ([request one]({rel('site/pages/sandbox.md', src)}) if you "
                            f"have none; [what is on it]({rel('site/pages/sandbox.md', src)}#what-is-on-your-site))."],
        "checks": lambda: [f"**Run the checks:** your own tests, the kit's checks and the money kit's release gate "
                           f"([testing and release]({rel('guide/14_testing_and_release.md', src)}#steps))."],
        "release": lambda: [f"**Release** through the customer's own release gate ({link('guide/14_testing_and_release.md')}); "
                            f"an app other shops install goes through the [App library]({rel('site/pages/publish.md', src)})."],
        "check-settings": lambda: [f"**Check it on your sandbox** as the people who will use it; where it touches a price or a "
                                   f"total, the money kit's release gate proves it ([testing and release]"
                                   f"({rel('guide/14_testing_and_release.md', src)}#steps))."],
        "release-settings": lambda: ["**Make the same settings on the customer's site**, from the list you wrote down, through "
                                     "the customer's own change process."],
        "more": lambda: ([f"**To lift a limit, ask for** " + " · ".join(f"[{h}]({request_url(h, c)})" for h in c.requests)
                          + f" (the extension-point request; {MEMBERS_ONLY})."] if c.requests else []),
        "ask": lambda: [f"**Ask for it:** " + " · ".join(f"[the extension-point request for {h}]({request_url(h, c)})" for h in c.requests)
                        + f" ({MEMBERS_ONLY}; [how requests work]({rel('guide/09_points_and_requests.md', src)}#asking-for-a-new-extension-point-or-for-more-from-one))."],
        "ask-us": lambda: [l for l in c.limits if l.startswith("**Ask us:**")],
        "until": lambda: ([f"**Until then, today:** {named(' '.join(TODAY.sub('', unbold(l)) for l in today))}"] if today else [])
                         + ([f"**Today's way round it:** {' · '.join(link(p) for p in c.paths('recipe') + c.paths('sample'))}."]
                            if c.paths("recipe") or c.paths("sample") else []),
        "instead": lambda: [l for l in c.limits if l.startswith("**Instead:**")],
    }
    key = f"{c.status}/{c.blocked_by}" if c.status == "not-yet" else c.status
    keys = [NO_CODE_STEPS.get(k, k) if c.door in NO_CODE else k for k in NEXT_STEPS.get(key, ())]
    steps = [s for k in keys for s in words[k]()]
    return [f"{n}. {s}" for n, s in enumerate(steps, 1)] + ([f"", f"*{DOOR_NEXT[c.door]}*"] if c.door in DOOR_NEXT else [])


# ── related needs ──────────────────────────────────────────────────────────────────────────────────────────────────
ARCHETYPES = "guide/15_customer_archetypes.md"


def named_together(root: pathlib.Path = ROOT) -> list[set[str]]:
    """The rows of chapter 15's tables that name two or more cards: needs a customer of that shape asks for together."""
    rows = [set(re.findall(r"needs/[a-z]+/([a-z0-9-]+)\.md", ln)) for ln in (root / ARCHETYPES).read_text("utf-8").splitlines()
            if ln.startswith("|")]
    return [r for r in rows if len(r) > 1]


def related_needs(cards: list, rows: list[set[str]]) -> dict:
    """Each card's related needs, at most four: its own `related:` line first, then the cards its text names (*the card
    <id>*), then those that cite one of its samples, those named with it in a row of chapter 15 (asked for together), those
    that cite one of its recipes, and the other cards of its topic. A sample is specific; a recipe such as the manifest's is
    cited by cards that have nothing else in common, so it comes after chapter 15."""
    by_id = {c.id: c for c in cards}
    out = {}
    for c in cards:
        same = lambda key: by_asks([o for o in cards if set(c.paths(key)) & set(o.paths(key))])
        together = [by_id[i] for r in rows if c.id in r for i in r if i in by_id]
        same_topic = [o for o in cards if o.area == c.area and o.topic == c.topic]
        picked: list = []
        named = [by_id[i] for i in NAMED_CARD.findall(c.text) if i in by_id]
        for o in [by_id[i] for i in c.related if i in by_id] + named + same("sample") + by_asks(together) + same("recipe") + by_asks(same_topic):
            if o.id != c.id and o not in picked:
                picked.append(o)
        out[c.id] = picked[:catalogue.MAX_RELATED]
    return out



def card_page(c, titles: dict, related: list = (), by_id: dict | None = None) -> GenPage:
    src = c.rel
    def proof(key: str) -> str:
        ps = c.paths(key)
        return " · ".join(f"[{proof_title(p, titles)}]({rel(p, src)})" for p in ps) or "none yet"
    lines = [f"# {c.title}", "", f"> The customer asks: *{c.asks}*", "",
             f"- **Verdict:** {c.verdict}",
             f"- **Door:** [{door_name(c.door)}](site:needs/door/{c.door}.html) · area: [{catalogue.AREAS[c.area]}](site:needs/{c.area}/index.html)"
             f" › [{topic_name(c)}](site:needs/{c.area}/index.html#{slug(topic_name(c))})",
             f"- **Recipe:** {proof('recipe')}", f"- **Sample:** {proof('sample')}"]
    if c.requests:
        lines.append(f"- **Request:** {', '.join(c.requests)} · [ask for an extension point]({rel('feedback/point_request.md', src)})")
    lines += [f"- **Checked:** {c.verified}", "", c.body.strip(), "", "## What next", ""] + step_lines(c, titles, src, by_id)
    if related:
        lines += ["", "## Related needs", ""] + [f"- {need_link(o, src)} — {o.verdict}" for o in related]
    lines += ["", f"[Start a project shortlist with this need](site:plan.html?needs={c.id}) · [Put it in your blueprint]"
              f"({rel('kit/blueprint.md', src)}) · [Every need](site:needs/index.html#a-to-z)"]
    build_words = seo.lead("# x\n\n" + c.sections.get("What you build", ""))
    desc = f"{c.title}: {c.verdict}. " + (build_words or f"The customer asks: {c.asks}.")
    return GenPage(src, f"needs/{c.area}/{c.id}.html", c.title, "\n".join(lines), desc)


def catalogue_pages(cards: list, titles: dict) -> list[GenPage]:
    cards = by_asks(cards)
    count = lambda pred: sum(1 for c in cards if pred(c))
    src = "needs/README.md"
    az, letter = [], ""
    for c in cards:
        first = az_key(c)[:1].upper()
        if first != letter:
            letter = first
            az += ["", f"### {letter}", ""]
        az.append(f"- {need_link(c, src)} — {c.verdict}")
    top = ["# Needs catalogue", "",
           "What retailers ask for, in their own words, and the answer for each: can you build it today, by which door, "
           "from which recipe and sample, and what to tell the customer. Start here when a customer sends you a list of needs. "
           f"[Plan a project](../site/pages/plan.md) shows the whole path from that list to a release.", "",
           "Type the need in the search box at the top of the page, find it in the **A to Z** list below (the customer's own words), "
           "or browse by area (each grouped by topic), by verdict or by door. "
           "Each card's verdict is one of four words: **Ready** · **Ready, with limits** (tell the customer each limit) · "
           "**Not yet** (it needs a new extension point or product work: the card says what to ask for) · **Not possible** "
           "(it breaks one of the four rules: the card says what to do instead). A need with no card: "
           f"[ask us](../feedback/point_request.md). At a terminal, `python3 tools/needs/needs.py search <words>` finds a card "
           "by its words, and the site's `catalogue.json` holds every card for an assistant.", "",
           "**Download:** [Needs at a glance](https://developer.ivendnext.com/downloads/needs_at_a_glance.pdf) (PDF: every need "
           "with its verdict and door, by area, to take into a customer meeting).", "",
           "## New and changed", "", "The cards checked most recently, newest first: a new need, or an answer run again.", ""]
    top += [f"- {need_link(c, src)} — {c.verdict} · {c.checked_on().isoformat()}" for c in newest(cards)]
    top += ["", "## Popular needs", "", popular(cards, src), "## By area", ""]
    top += [f"- [{name}](site:needs/{a}/index.html) ({count(lambda c, a=a: c.area == a)})" for a, name in catalogue.AREAS.items()]
    top += ["", "## By verdict", ""]
    top += [f"- [{word}](site:needs/status/{st}.html) ({count(lambda c, st=st: c.status == st)})" for st, word in catalogue.STATUSES.items()]
    top += ["- [What is not possible, and what to do instead](site:needs/not-possible.html)", "",
            "## By door", "", "How each need is built. The guide's chapter 3 gives the order to try them in: configure first.", ""]
    top += [f"- [{door_name(d)}](site:needs/door/{d}.html) ({count(lambda c, d=d: c.door == d)})"
            for d in catalogue.DOORS if any(c.door == d for c in cards)]
    top += ["", "## All needs on one page", "", "[Every card in full on one page](site:needs/all.html), for your browser's find.",
            "", "## A to Z"] + az
    pages = [GenPage(src, "needs/index.html", "Needs catalogue", "\n".join(top),
                     "What retailers ask for, in their own words, and whether each can be built on iVendNext today: the verdict, the door, the recipe and the limits.")]
    for a, name in catalogue.AREAS.items():
        pages.append(area_page(a, name, [c for c in cards if c.area == a]))
    for st, word in catalogue.STATUSES.items():
        mine = [c for c in cards if c.status == st]
        pages.append(GenPage(f"needs/status/{st}.md", f"needs/status/{st}.html", f"Needs: {word.lower()}",
                             f"# Needs: {word.lower()}\n\n{len(mine)} needs. [All needs](site:needs/index.html).\n\n" + need_table(mine, f"needs/status/{st}.md"),
                             f"Every need in the iVendNext Developers catalogue whose verdict is {word.lower()}, each with the card that says what to do about it."))
    for d in catalogue.DOORS:
        mine = [c for c in cards if c.door == d]
        if not mine:
            continue
        guide = DOOR_HOW.get(d, "guide/09_points_and_requests.md")
        how = f" How it works: [{titles.get(guide, guide)}]({rel(guide, f'needs/door/{d}.md')})."
        pages.append(GenPage(f"needs/door/{d}.md", f"needs/door/{d}.html", f"Needs by door: {door_name(d).lower()}",
                             f"# Needs by door: {door_name(d).lower()}\n\n{len(mine)} needs.{how} [All needs](site:needs/index.html).\n\n"
                             + need_table(mine, f"needs/door/{d}.md"),
                             f"Every need in the iVendNext Developers catalogue {("built through the door called " + door_name(d).lower()) if d != "none" else "that has no door"}, with its verdict and the card for each."))
    full = ["# All needs", "", "Every card in full, by area, for your browser's find. [The catalogue](site:needs/index.html) · "
            "[the A to Z list](site:needs/index.html#a-to-z).", ""]
    for a, name in catalogue.AREAS.items():
        full += [f"## {name}", ""]
        for c in [c for c in cards if c.area == a]:
            body = re.sub(r"^## (.+)$", r"**\1.**", c.body.strip(), flags=re.M)
            full += [f"### {c.title}", "", f"*{c.asks}* — **{c.verdict}** · {door_name(c.door)} · [the card]({rel(c.rel, 'needs/all.md')})", "", body, ""]
    pages.append(GenPage("needs/all.md", "needs/all.html", "All needs", "\n".join(full),
                         "Every card of the iVendNext Developers needs catalogue in full on one page, for your browser's find: the verdict, the door, the recipe and the limits."))
    np = ["# What is not possible, and what to do instead", "",
          "Needs iVendNext cannot meet today. **Not yet** means a new extension point (ask for it with the request named on the card) "
          "or product work on our side (ask us). **Not possible** means it breaks one of the four rules (guide chapter 3); "
          f"the card says what to do instead. [Ask for an extension point](../feedback/point_request.md).", ""]
    groups = [("Not yet: an extension point to ask for", lambda c: c.status == "not-yet" and c.blocked_by == "extension-point"),
              ("Not yet: product work on our side", lambda c: c.status == "not-yet" and c.blocked_by == "product-work"),
              ("Not possible", lambda c: c.status == "not-possible")]
    for head, pred in groups:
        mine = [c for c in cards if pred(c)]
        np += [f"## {head}", "", "| The customer asks | What to do |", "|---|---|"]
        np += [f"| {need_link(c, 'needs/not-possible.md')} | " + " ".join(l.replace("**", "") for l in c.limits)
               + (f" Ask for {', '.join(c.requests)}." if c.requests else "") + " |" for c in mine]
        np.append("")
    pages.append(GenPage("needs/not-possible.md", "needs/not-possible.html", "What is not possible", "\n".join(np),
                         "The needs iVendNext cannot meet today, and what to do instead: an extension point to ask for, product work to request, or another way."))
    return pages


def area_page(a: str, name: str, mine: list) -> GenPage:
    """An area's page: its popular cards first, then every card under its topic's heading, with the topics as anchors on top."""
    src = f"needs/{a}/index.md"
    topics = [(t, label) for t, label in catalogue.TOPICS.get(a, {}).items() if any(c.topic == t for c in mine)]
    lines = [f"# Needs: {name.lower()}", "", f"{len(mine)} needs under {len(topics)} topics. [All areas](site:needs/index.html).", "",
             "**Topics:** " + " · ".join(f"[{label}](#{slug(label)})" for _, label in topics), ""]
    pop = popular(mine, src)
    if pop:
        lines += ["## Popular in this area", "", pop]
    for t, label in topics:
        lines += [f"## {label}", "", need_table([c for c in mine if c.topic == t], src)]
    return GenPage(src, f"needs/{a}/index.html", f"Needs: {name.lower()}", "\n".join(lines),
                   f"What retailers ask for in {name.lower()}, grouped by topic, and whether each can be built on iVendNext today, with its recipe and limits.")


def popular(cards: list, src: str) -> str:
    return "".join(f"- {need_link(c, src)} — {c.verdict}\n" for c in cards if c.popular == "yes")


def catalogue_json(cards: list, titles: dict | None = None, pages: dict | None = None, related: dict | None = None) -> str:
    """Every card for an assistant and for Plan a project (site/assets-src/plan.js): the card's own fields, then what the
    shortlist needs: its door's name and topic's label, its build step and why, its recipes and samples with their titles
    and pages, the request form for each handle, its related needs, and its blueprint row as `needs.py blueprint` prints
    it, without the row number (the shortlist numbers the rows it joins)."""
    import json
    titles, pages, related = titles or {}, pages or {}, related or {}

    def proofs(c, kind):                     # a page of this site, or (a contract page, a tool) the file in the kit on GitHub
        out = []
        for p in c.paths(kind):
            key, f = p.rstrip("/"), ROOT / p.rstrip("/")
            title = proof_title(p, titles)
            url = "" if key in pages else f"{REPO_URL}/{'tree' if f.is_dir() else 'blob'}/main/{key}"
            out.append({"path": p, "title": title, "page": pages.get(key, ""), "url": url})
        return out
    return json.dumps([{"id": c.id, "title": c.title, "area": c.area, "asks": c.asks, "status": c.status, "verdict": c.verdict,
                        "topic": c.topic, "door": c.door, "blocked_by": c.blocked_by, "recipe": c.recipe, "sample": c.sample,
                        "request": c.requests, "verified": c.verified, "limits": c.limits,
                        "tell": c.sections.get("Tell the customer", ""), "page": f"needs/{c.area}/{c.id}.html",
                        "door_name": door_name(c.door), "topic_name": topic_name(c),
                        "build_step": build_step(c.door), "build_why": build_why(c.door),
                        "recipes": proofs(c, "recipe"), "samples": proofs(c, "sample"),
                        "request_forms": [{"handle": h, "url": request_url(h, c), "note": MEMBERS_ONLY} for h in c.requests],
                        "related": [o.id for o in related.get(c.id, [])],
                        "blueprint_row": catalogue.blueprint_rows([c], [c.id])[0][0].removeprefix("| 1 ")}
                       for c in by_asks(cards)], indent=1, ensure_ascii=False) + "\n"


def plan_tool(here: str) -> str:
    """The shortlist builder on Plan a project (site/assets-src/plan.js fills it). It stays hidden until the script shows it,
    so without script the page is its seven steps and the link to the blueprint. The blueprint's header comes from needs.py."""
    up = "../" * (here.count("/") + 1) if here else ""
    e = lambda s: html.escape(s, quote=True)
    return (f'<section id="plan-tool" class="plan-tool" data-root="{up}" data-head="{e(catalogue.BLUEPRINT_HEAD)}" hidden>'
            '<h2 id="build-the-shortlist">Build the shortlist</h2>'
            "<p>Find each of the customer's needs and tick it. The shortlist below gives the order to build them in, the recipes "
            "and samples once each, the limits to tell the customer and the requests to file. It lives in this page's address: "
            "copy the address to send it to a colleague.</p>"
            '<p class="plan-q"><label for="plan-q">Find a need</label>'
            '<input id="plan-q" type="search" autocomplete="off" spellcheck="false" placeholder="In the customer\'s words"></p>'
            '<ul id="plan-found" class="plan-list" aria-live="polite"></ul>'
            '<div id="plan-out" aria-live="polite"></div></section>'
            f'<script src="{up}assets/plan.js" defer></script>')


HOSTING_API = "https://hosting.ivendnext.app"            # the hosting's web door: hosting.js calls only this
OWN_POLICY = {"hosting.html"}                              # pages that carry their own content policy, no site-wide scripts


def hosting_tool(here: str) -> str:
    """Host your app from the page (HOSTWEB): site/assets-src/hosting.js fills it. Hidden until the script shows it, so
    without script the page is its text and the kit's command."""
    up = "../" * (here.count("/") + 1) if here else ""
    return (f'<section id="hosting-tool" class="hosting-tool" data-publish="{PUBLISH_PAGE}" hidden></section>'
            f'<script src="{up}assets/hosting.js" defer></script>')


def page_policy() -> str:
    """The hosting page's own content policy, in place of the site-wide one: its one script, and the one address it may
    reach (the hosting's web door). No counter and no search script on it: the page that holds a sign-in runs nothing
    else. A meta tag cannot send frame-ancestors: hosting.js refuses to run inside a frame."""
    return "; ".join(["default-src 'self'", "script-src 'self'", f"connect-src {HOSTING_API}", "img-src 'self' data:",
                      "font-src 'self'", "style-src 'self'", "object-src 'none'", "base-uri 'self'",
                      "form-action 'self'"])


# ── the search index ───────────────────────────────────────────────────────────────────────────────────────────────
SYNONYMS = SITE / "synonyms.txt"
SEARCH_GROUPS = {"recipes": "recipe", "samples": "sample"}       # every other page is a guide page in the results


def synonyms(path: pathlib.Path = SYNONYMS) -> list[list[str]]:
    """site/synonyms.txt: one group of words a customer uses for the same thing per line, comma-separated."""
    return [[t.strip().lower() for t in line.split(",")] for line in path.read_text("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def synonym_errors(groups: list[list[str]]) -> list[str]:
    bad, seen = [], {}
    for n, g in enumerate(groups, 1):
        if len([t for t in g if t]) < 2 or not all(g):
            bad.append(f"site/synonyms.txt group {n}: a group holds two or more words and no empty one: {', '.join(g)}")
        for t in g:
            if t and t in seen:
                bad.append(f"site/synonyms.txt: '{t}' is in group {seen[t]} and group {n}; a word belongs to one group")
            seen.setdefault(t, n)
    return bad


def synonym_pattern(term: str) -> re.Pattern:      # the term as a whole word or phrase, a plural "s" or "es" allowed (not on two letters)
    words = [re.escape(w) for w in re.split(r"[\s-]+", term)]
    plural = r"(?:s|es)?" if len(term) > 2 else ""          # "po" is not "pos"
    return re.compile(r"(?<![a-z0-9])" + r"[\s-]+".join(words) + plural + r"(?![a-z0-9])")


def expand(text: str, groups: list[list[str]]) -> str:
    """Every word of every group one of whose words is in `text`: the card's words a customer may type instead."""
    low = text.lower()
    return " ".join(t for g in groups if any(synonym_pattern(w).search(low) for w in g) for t in g)


def plain(md: str) -> str:                       # Markdown to the words a reader sees
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    return re.sub(r"\s+", " ", re.sub(r"[`*_>|#]", " ", md)).strip()


def page_words(text: str) -> tuple[list[str], str]:
    """A kit page's headings (levels 2 and 3, outside code) and its first two paragraphs of prose, at most 600 characters."""
    heads, paras = [], []
    for block in re.split(r"\n\s*\n", re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)):
        heads += [plain(h) for h in re.findall(r"^#{2,3} (.+)$", block, re.M)]
        rest = "\n".join(ln for ln in block.splitlines() if not ln.startswith("#")).strip()
        if len(paras) < 2 and rest and not rest.startswith(("|", "{", "!", "<")):
            paras.append(plain(rest))
    return heads, " ".join(paras)[:600]


ASKED_PAGES = {"questions.html"}                   # pages whose ### headings are questions in the asker's own words: they count as
                                                   # the page's asks line, as a card's does (Questions developers ask)
# Two pages answer a developer's question without ### headings; their asks line is written here, in the developer's words, so
# the header's six show them for "screen", "field" and "loyalty" ahead of the recipes that also use those words (HOWITWORKS-CHECK).
ASKS_ADDED = {
    "map.html": "Is there a list of all the endpoints my app can call? Which record types and fields can my app read or change, "
                "and which are required or read-only? Which screens can my app add, on the till and in the back office?",
    "guide/01c_how_the_data_travels.html": "A chain has its own loyalty system outside iVendNext: which calls go where on each sale, "
                "and how does the reward get onto the sale? How does a phone retailer link the till to a telecom provider "
                "for plan prices and activation?",
}


def search_docs(pages: list, cards: list, groups: list[list[str]], records: list = ()) -> list[dict]:
    """The documents search.js ranks: one per card, then one per guide, recipe and sample page (the home page and the site's
    own catalogue lists are not in it: every card is). Short keys keep the file small: k kind · t title · a asks · s synonyms ·
    tp topic · l limits · c tell the customer · b body · u the page · v verdict · ar area · d door · st status."""
    docs = []
    for c in by_asks(cards):
        docs.append({"id": f"needs/{c.area}/{c.id}.html", "k": "need", "t": c.title, "a": c.asks,
                     "s": expand(f"{c.asks} {c.title} {topic_name(c)}", groups), "tp": topic_name(c),
                     "l": " ".join(plain(l) for l in c.limits), "c": plain(c.sections.get("Tell the customer", "")),
                     "b": plain(c.sections.get("What you build", "")), "u": f"needs/{c.area}/{c.id}.html",
                     "v": c.verdict, "ar": c.area, "d": c.door, "st": c.status})
    for p in pages:
        if p.out == "index.html":
            continue
        heads, first = page_words(p.text)
        asks = " ".join(plain(q) for q in re.findall(r"^### (.+)$", p.text, re.M)) if p.out in ASKED_PAGES else ASKS_ADDED.get(p.out, "")
        docs.append({"id": p.out, "k": SEARCH_GROUPS.get(p.group, "guide"), "t": p.title, "a": asks,
                     "s": expand(p.title + " " + " ".join(heads), groups), "tp": "", "l": "", "c": "",
                     "b": " · ".join(heads) + " " + first, "u": p.out, "v": "", "ar": "", "d": "", "st": ""})
    for g in records:                              # a record type: its name and first paragraph, no synonyms, so a guide or recipe
        first = g.desc                             # that answers a word ("loyalty") still leads; the index takes the developer's words
        words = expand("record type fields doctype", groups) if g.out == "records/index.html" else ""
        docs.append({"id": g.out, "k": "guide", "t": g.title, "a": "", "s": words, "tp": "", "l": "", "c": "", "b": first,
                     "u": g.out, "v": "", "ar": "", "d": "", "st": ""})
    return docs


def search_page() -> str:
    """search.html's body: the box, the three filters (needs only), and the place search.js writes the results."""
    opts = lambda name, label, items: (f'<p class="filter"><label for="f-{name}">{label}</label><select id="f-{name}" name="{name}">'
                                       f'<option value="">Any</option>' + "".join(
                                           f'<option value="{k}">{html.escape(v)}</option>' for k, v in items) + "</select></p>")
    return ('<h1>Search</h1>'
            '<form class="search-page" action="search.html" method="get" role="search">'
            '<p class="search-q"><label for="q-page">Search for</label><input id="q-page" name="q" type="search" autocomplete="off" spellcheck="false">'
            '<button class="site-btn" type="submit">Search</button></p>'
            '<fieldset class="search-filters"><legend>Narrow the needs</legend>'
            + opts("area", "Area", catalogue.AREAS.items()) + opts("door", "Door", catalogue.DOORS.items())
            + opts("status", "Verdict", catalogue.STATUSES.items()) + '</fieldset></form>'
            '<noscript><p>This page works with your browser\'s script turned on. Without it, open '
            '<a href="needs/all.html">every need on one page</a> and use your browser\'s find, or read the '
            '<a href="needs/index.html#a-to-z">A to Z list</a>.</p></noscript>'
            '<div id="search-results" aria-live="polite"></div>')


def needs_served(page, served: dict, up: str) -> str:
    """The "Needs this serves" list under a recipe or a sample page: the cards that cite it."""
    key = page.src.removesuffix("/README.md") if page.group == "samples" else page.src
    cards = served.get(key, [])
    if not cards:
        return ""
    items = "".join(f'<li><a href="{up}needs/{c.area}/{c.id}.html">{html.escape(c.asks)}</a> — {html.escape(c.verdict)}</li>'
                    for c in by_asks(cards))
    return f'<section class="served"><h2 id="needs-this-serves">Needs this serves</h2><ul>{items}</ul></section>'


def card_sources(c, related: dict) -> list[str]:
    """The files a card's page is made from: the card, the cards it lists as related, and the recipes and samples it names (their
    titles are on the page)."""
    proofs = [p if p.endswith(".md") else p.rstrip("/") + "/README.md" for p in c.paths("recipe") + c.paths("sample")]
    return [c.rel] + [o.rel for o in related.get(c.id, [])] + proofs


def not_found_body(cards: list) -> str:
    """The 404 page: a search box, the three ways in, and every need in the customer's words, A to Z. Absolute addresses, since
    the page is served from any address."""
    letters: dict[str, list] = {}
    for c in by_asks(cards):
        letters.setdefault(az_key(c)[:1].upper(), []).append(c)
    az = "".join(f'<h3>{l}</h3><ul class="plain">' + "".join(
        f'<li><a href="/needs/{c.area}/{c.id}.html">{html.escape(c.asks)}</a></li>' for c in cs) + "</ul>" for l, cs in letters.items())
    return ('<h1>Page not found</h1><p>That page is not on this site. Search for what you wanted, or start from one of the three places below.</p>'
            '<form class="search-page" action="/search.html" method="get" role="search"><p class="search-q">'
            '<label for="q-404">Search for</label><input id="q-404" name="q" type="search" autocomplete="off" spellcheck="false">'
            '<button class="site-btn" type="submit">Search</button></p></form>'
            '<ul class="plain"><li><a href="/needs/index.html">A customer sent me a list of needs</a></li>'
            '<li><a href="/build.html">I know what I\'m building</a></li><li><a href="/start.html">I\'m new</a></li></ul>'
            f'<h2>Every need, A to Z</h2>{az}')


def build(out_dir: pathlib.Path) -> int:
    pages = collect()
    need_cards = catalogue.load(ROOT)
    titles = {p.src: p.short for p in pages} | {posixpath.dirname(p.src): p.short for p in pages if p.src.endswith("/README.md")}
    related = related_needs(need_cards, named_together())
    by_id = {c.id: c for c in need_cards}
    gen = [card_page(c, titles, related[c.id], by_id) for c in need_cards] + catalogue_pages(need_cards, titles)
    rec_pages = [GenPage(src, out, title, text, desc, "records") for src, out, title, text, desc in devmap.record_pages()]
    registry = {p.src: p for p in pages}
    registry.update({p.src: p for p in gen if p.src.startswith("needs/") and p.out.count("/") == 2 and not p.out.endswith("index.html")})
    registry.update({"needs/README.md": gen[len(need_cards)], "needs": gen[len(need_cards)]})       # the catalogue
    registry.update({f"needs/{p.out.split('/')[1]}": p for p in gen if re.fullmatch(r"needs/[a-z]+/index\.html", p.out)})   # an area's folder
    lists = [ListPage("recipes/index.html", "recipes"), ListPage("samples/index.html", "samples")]
    registry.update({posixpath.dirname(p.src): p for p in pages if p.src.endswith("/README.md")})   # a link to a sample's folder opens its page
    registry.update({"recipes": lists[0], "samples": lists[1]})         # a link to either folder lands on its list page
    errors: list[str] = []
    assets: set[str] = set()
    ctx = Ctx(registry, out_dir, errors, assets)
    ctx.cards = need_cards
    errors += [f"needs: {e}" for e in catalogue.check(ROOT)]
    errors += order_errors()
    errors += devmap.errors()
    errors += label_errors(pages) + example_errors(need_cards)
    groups = synonyms()
    errors += synonym_errors(groups)
    served = catalogue.backlinks(need_cards)
    ctx.samples = gallery.collect(pages, served, catalogue.DOORS, first_use, slug, ROOT, errors)
    ctx.door_pages = {c.door for c in need_cards}
    assets.update(s["shot"] for s in ctx.samples if s["shot"])
    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    def write(rel: str, text: str) -> None:
        f = out_dir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, "utf-8")

    # ── what each page tells a search engine (site/seo.py): its title, description, place, kind and last-changed date ──
    seo_data, seo_errors = seo.load(SEO_JSON)
    errors += seo_errors
    dates = seo.git_dates(ROOT)
    if dates is None:
        if os.environ.get("SITE_REQUIRE_OPTIONAL") == "true":
            errors.append("sitemap lastmod: a deploy build needs the whole git history (fetch-depth: 0 in the workflow)")
        else:
            print("  no lastmod in the sitemap: the git history is not whole (a shallow clone) or git cannot be read")
    card_srcs = [c.rel for c in need_cards]
    sample_srcs = [p.src for p in pages if p.group == "samples"]
    card_outs = {f"needs/{c.area}/{c.id}.html" for c in need_cards}
    metas: dict[str, seo.PageMeta] = {}
    sources: dict[str, list[str]] = {}
    originals: dict[str, str] = {}
    hand = seo_data["descriptions"]

    def kinds(out: str, group: str) -> tuple[str, str]:                 # (description kind, preview image)
        if out in card_outs:
            return "card", "card"
        if group == "guide" and out == "guide/index.html":
            return "page", "guide"
        return {"needs": ("needs", "needs"), "guide": ("guide", "guide"), "recipes": ("recipe", "recipes"),
                "samples": ("sample", "samples"), "feedback": ("feedback", "home")}.get(group, ("page", "home"))

    def trail_for(out: str, name: str, group: str) -> list:             # the page's place, below Home
        if out in ("index.html", "404.html", "search.html"):
            return []
        if group == "needs":
            top = [("Needs", "needs/index.html")]
            if out == "needs/index.html":
                return top
            area = re.fullmatch(r"needs/([a-z]+)/(index|[^/]+)\.html", out)
            if area and area.group(1) in catalogue.AREAS:
                a = (catalogue.AREAS[area.group(1)], f"needs/{area.group(1)}/index.html")
                return top + [a] if area.group(2) == "index" else top + [a, (name, out)]
            return top + [(name, out)]
        if group in GROUPS:
            idx = f"{group}/index.html"
            return [(GROUPS[group], idx)] if out == idx else [(GROUPS[group], idx), (name, out)]
        return [(name, out)]

    def make_meta(out: str, name: str, group: str, text: str, srcs: list[str]) -> seo.PageMeta:
        kind, image = kinds(out, group)
        m = seo.PageMeta(name=seo_data.get("titles", {}).get(out, name), desc=hand.get(out) or seo.fit(text, kind), kind=kind, image=image,
                         trail=trail_for(out, name, group), modified=seo.newest(dates, srcs), home=(out == "index.html"))
        metas[out], sources[out] = m, srcs
        originals[out] = name
        return m

    def page_sources(p: Page) -> list[str]:                             # the page's file, the sections it pulls in, the cards it lists
        srcs = [p.src] + re.findall(r"^\{\{include\??\s+([^\s#}]+)", p.text, re.M)
        if p.group in ("recipes", "samples"):                           # its "Needs this serves" list: the cards that cite it
            srcs += [c.rel for c in served.get(p.src.removesuffix("/README.md") if p.group == "samples" else p.src, [])]
        if "{{needs:" in p.text:
            srcs += card_srcs
        if "{{samples:" in p.text:
            srcs += sample_srcs
        return srcs

    for p in pages:
        ctx.src, ctx.out = p.src, p.out
        toc: list = []
        p.html = render(p.text, ctx, {}, toc)
        up = up_of(p.out)
        src_link = ("" if p.src.startswith("site/pages/")
                    else f'<p class="src"><a href="{REPO_URL}/blob/main/{p.src}">This page in the kit</a></p>')
        hero, body = hero_of(p.html) if p.out == "index.html" else ("", p.html)
        served_html = needs_served(p, served, up) if p.group in ("recipes", "samples") else ""
        meta = make_meta(p.out, p.title, p.group, seo.lead(p.text), page_sources(p))
        write(p.out, shell(p.title, body, p.out, side=sidebar(p, pages, lists, up), toc=toc, hero=hero,
                           foot=served_html + prev_next(p, pages, up) + src_link, sha=sha, meta=meta,
                           crumbs=seo.crumbs_html(meta.trail, up), verify=seo_data))

    for g in gen:                                                   # the catalogue's pages, from the cards
        ctx.src, ctx.out = g.src, g.out
        toc = []
        g.html = render(g.text, ctx, {}, toc)
        up = up_of(g.out)
        src_link = (f'<p class="src"><a href="{REPO_URL}/blob/main/{g.src}">This card in the kit</a></p>'
                    if g.src.count("/") == 2 and (ROOT / g.src).exists() else "")
        area = re.fullmatch(r"needs/([a-z]+)/index\.html", g.out)
        srcs = (card_sources(by_id[g.out.split("/")[2].removesuffix(".html")], related) if g.out in card_outs
                else [f"needs/{area.group(1)}/"] if area else ["needs/"])      # a list is dated by any change under its folder, a removal too
        meta = make_meta(g.out, g.title, g.group, g.desc, srcs)
        write(g.out, shell(g.title, g.html, g.out, side=sidebar(g, pages, lists, up), toc=toc, foot=src_link, sha=sha, meta=meta,
                           crumbs=seo.crumbs_html(meta.trail, up), verify=seo_data))
    for g in rec_pages:                                             # the record types, from api/records/ (tools/records/)
        ctx.src, ctx.out = g.src, g.out
        toc = []
        g.html = render(g.text, ctx, {}, toc)
        up = up_of(g.out)
        data = g.src.removesuffix(".md") + ".json"
        srcs = [data, "tools/records/records.py"] if (ROOT / data).exists() else ["api/records/", "tools/records/records.py"]
        src_link = f'<p class="src"><a href="{REPO_URL}/blob/main/{data}">This record type in the kit</a></p>' if (ROOT / data).exists() else ""
        meta = make_meta(g.out, g.title, g.group, g.desc, srcs)
        write(g.out, shell(g.title, g.html, g.out, side=sidebar(g, pages, lists, up), toc=toc, foot=src_link, sha=sha, meta=meta,
                           crumbs=seo.crumbs_html(meta.trail, up), verify=seo_data))
    proof_pages = {k: v.out for k, v in registry.items() if isinstance(v, (Page, ListPage)) and k != "recipes" and k != "samples"}
    write("catalogue.json", catalogue_json(need_cards, titles, proof_pages, related))
    import json
    write("search-index.json", json.dumps(search_docs(pages, need_cards, groups, rec_pages), ensure_ascii=False, separators=(",", ":")) + "\n")
    write("search.html", shell("Search", search_page(), "search.html", sha=sha, noindex=True,
                               desc="Search the iVendNext Developers site: the needs catalogue first, then the recipes, samples and guide."))

    rec = [p for p in pages if p.group == "recipes" and p.out != "recipes/index.html"]
    body = ("<h1>Recipes</h1><p>One recipe for each job. Each says what it does and who it is for, gives the steps with "
            "their commands, and says what is refused.</p><ul class=\"plain\">"
            + "".join(f'<li><a href="{posixpath.basename(p.out)}">{html.escape(p.short)}</a></li>' for p in rec) + "</ul>")
    meta = make_meta("recipes/index.html", "Recipes", "recipes", "One recipe for each job on iVendNext: what it does, who it is for, "
                     "the steps with their commands, and what is refused.", ["recipes/"])
    write("recipes/index.html", shell("Recipes", body, "recipes/index.html", side=sidebar(lists[0], pages, lists, "../"), sha=sha, meta=meta,
                                      crumbs=seo.crumbs_html(meta.trail, "../"), verify=seo_data))
    body = ("<h1>Samples</h1><p>Each sample is a small working example of one way in, with its tests. Pick the nearest one to "
            "your project, run it against your sandbox, and change it. Each card gives the door the sample uses and its first "
            "commands, and opens the sample's own page: what it does, how to run it and what its tests prove. "
            "The same cards are on the <a href=\"../reference_apps.html\">reference apps page</a>, grouped by door.</p>"
            + gallery.flat(ctx.samples, "samples", REPO_URL, catalogue.DOORS, ctx.door_pages))
    meta = make_meta("samples/index.html", "Samples", "samples", "Small working examples of each way into iVendNext, with their "
                     "tests: pick the nearest to your project and run it against your sandbox.", [("samples/", "README.md")])
    write("samples/index.html", shell("Samples", body, "samples/index.html", side=sidebar(lists[1], pages, lists, "../"), sha=sha, meta=meta,
                                      crumbs=seo.crumbs_html(meta.trail, "../"), verify=seo_data))

    for name in ("site.css", "favicon.svg"):
        write("assets/" + name, (SITE / name).read_text("utf-8"))
    write("assets/ivn-kit.css", (ROOT / "kit/design/ivn-kit.css").read_text("utf-8"))
    for f in sorted((SITE / "assets-src").rglob("*")):                # the logo, the font and the preview images, as bytes
        if f.is_file():
            dest = out_dir / "assets" / f.relative_to(SITE / "assets-src")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    write("404.html", shell("Page not found", not_found_body(need_cards), "404.html", absolute=True, noindex=True,
                            desc="That page is not on the iVendNext Developers site. Search it, start from one of three places, or read the A to Z list of needs."))

    # ── the checks a search engine would make of us ──
    for kind in seo.OG_KINDS:
        if not (SITE / "assets-src" / "og" / f"{kind}.png").is_file():
            errors.append(f"site/assets-src/og/{kind}.png is missing (draw it with site/og/draw.py)")
    errors += seo.desc_problems({o: m.desc for o, m in metas.items()})
    unknown = sorted(set(hand) - set(metas))
    errors += [f"site/seo.json: a description for {o}, which is not a page of the site" for o in unknown]
    errors += [f"site/seo.json: a title for {o}, which is not a page of the site" for o in sorted(set(seo_data.get("titles", {})) - set(metas))]
    errors += [f"site/seo.json: a title for {o}, whose own heading is {len(seo.title_of(originals[o]))} characters: a hand-written title is only for a heading over {seo.FAIL_TITLE_OVER}"
               for o in seo_data.get("titles", {}) if o in originals and (len(seo.title_of(originals[o])) <= seo.FAIL_TITLE_OVER or o in card_outs)]
    bad_titles, warn_titles = seo.title_problems({o: seo.title_of(m.name, m.home) for o, m in metas.items()})
    errors += bad_titles
    for w in warn_titles:
        print("  warning:", w)
    for o, m in metas.items():                                      # a breadcrumb names pages that exist
        errors += [f"{o}: the breadcrumb names {t}, which is not a page of the site" for _, t in m.trail if t not in metas]

    # ── redirects: a moved page is a small stub that names the new address ──
    for old, new in seo.read_redirects(REDIRECTS):
        if not old.endswith(".html") or new not in metas:
            errors.append(f"site/redirects.txt: '{old} {new}' needs an old address ending in .html and a new address that is a page the build makes")
        elif old in metas or (out_dir / old).exists():
            errors.append(f"site/redirects.txt: {old} is a page of the site; a stub would replace it")
        else:
            write(old, seo.redirect_stub(old, new))

    # ── sitemap, robots.txt, llms.txt ──
    write("sitemap.xml", seo.sitemap({canonical(o): m.modified for o, m in metas.items()}))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: https://{DOMAIN}/sitemap.xml\n")

    START = ["index.html", "start.html", "build.html", "plan.html", "sandbox.html", "security.html", "map.html", "api.html", "hosting.html",
             "publish.html",
             "reference_apps.html", "feedback.html"]

    def rows(pred) -> list[tuple[str, str, str]]:
        picked = [(o, m) for o, m in metas.items() if pred(o, m)]
        picked.sort(key=lambda om: START.index(om[0]) if om[0] in START else 0)        # the top-level pages in reading order
        return [(seo.SITE_NAME if m.home else seo.clean_name(m.name), canonical(o), m.desc) for o, m in picked]
    ai = metas.get("guide/13_ai.html")
    write("llms.txt", seo.llms_txt([
        ("Start here", rows(lambda o, m: "/" not in o)),
        ("Needs", rows(lambda o, m: o.startswith("needs/") and re.fullmatch(r"needs/(index|not-possible|[a-z]+/index)\.html", o) is not None)),
        ("Guide", rows(lambda o, m: o.startswith("guide/") or o == "kit/blueprint.html")),
        ("Recipes", rows(lambda o, m: o.startswith("recipes/"))),
        ("Samples", rows(lambda o, m: o.startswith("samples/"))),
        ("Record types", rows(lambda o, m: o.startswith("records/"))),
        ("Machine-readable", [("The needs catalogue as JSON", f"https://{DOMAIN}/catalogue.json",
                               "Every need card with its verdict, door, recipes, samples and limits, for an assistant."),
                              ("The AI chapter", canonical("guide/13_ai.html"), ai.desc if ai else "How to use an assistant with the kit."),
                              ("Sitemap", f"https://{DOMAIN}/sitemap.xml", "Every indexed page of the site.")])]))
    write("downloads/blueprint_template.md", (ROOT / "kit/blueprint_template.md").read_text("utf-8"))   # to fill on screen; the PDFs: site/pdf/
    write("downloads/blueprint_example.md", (ROOT / EXAMPLE).read_text("utf-8"))
    write("CNAME", DOMAIN + "\n")
    write(".nojekyll", "")
    for rel in sorted(assets):
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, out_dir / rel)
    if errors:
        print("SITE BUILD FAILED:\n  " + "\n  ".join(sorted(set(errors))))
        return 1
    print(f"site built: {len(metas) + 2} pages ({len(need_cards)} needs), {len(assets)} images -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(build(pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SITE / "_out"))
