"""site/seo.py — what makes the developer site findable: titles, descriptions, structured data, preview images, sitemap dates,
llms.txt, redirects. build.py calls it; test_site.py holds it (each rule shown red on a planted fault).

  - Titles: the site name is iVendNext Developers. The home page has its own title; any other page is "<name> · iVendNext
    Developers" when that is at most 65 characters, otherwise the name alone. A guide chapter's number is left out.
  - Descriptions: 120 to 160 characters. The pages that matter are written by hand in site/seo.json; the rest by rule (the
    page's first sentences, then a sentence for its kind if the page says too little).
  - Structured data: one JSON-LD block per page, from data the page shows (Organization and WebSite on the home page,
    BreadcrumbList under it, TechArticle on guide, recipe, sample and card pages). Never FAQ or HowTo markup.
  - Preview images: one of six pictures (site/assets-src/og/) by the kind of page.
  - lastmod: the date of the last commit to the page's source files, never the build time; none if the history is not whole.
  - Search-engine verification values come from site/seo.json when marketing sets them; the build never invents one.
"""
from __future__ import annotations

import html
import json
import pathlib
import posixpath
import re
import subprocess
from dataclasses import dataclass, field

SITE_NAME = "iVendNext Developers"
DOMAIN = "developer.ivendnext.com"
HOME_TITLE = "iVendNext Developers: build custom retail POS apps, integrations and extensions"
CORP = "https://www.ivendnext.com/"
LIBRARY = "https://library.ivendnext.app"            # the product's other public site: the footer's link
MAX_TITLE, WARN_TITLE_OVER, FAIL_TITLE_OVER = 65, 65, 90
MIN_DESC, MAX_DESC = 120, 160
OG_SIZE = (1200, 630)
OG_KINDS = ("home", "needs", "guide", "recipes", "samples", "card")
OG_ALT = {"home": "iVendNext Developers: build custom retail POS apps, integrations and extensions",
          "needs": "iVendNext Developers needs catalogue: what retailers ask for, and whether it can be built today",
          "guide": "iVendNext Developers guide: the ladder of ways in, chapter by chapter",
          "recipes": "iVendNext Developers recipes: one recipe for each job, with its steps and commands",
          "samples": "iVendNext Developers samples: small working examples of each way in, with their tests",
          "card": "An iVendNext Developers needs card: the customer's words, the verdict and the way to build it"}
KIND_SENTENCE = {"guide": "A chapter of the iVendNext Developers guide.", "recipe": "A recipe for builders on iVendNext.",
                 "sample": "A sample for builders on iVendNext, with its tests.",
                 "card": "A card in the iVendNext Developers needs catalogue.",
                 "needs": "A list in the iVendNext Developers needs catalogue.",
                 "feedback": "A form on the iVendNext Developers site.", "page": "A page of the iVendNext Developers site."}
TECH_KINDS = {"guide", "recipe", "sample", "card"}
ALLOWED_LD_TYPES = {"Organization", "WebSite", "BreadcrumbList", "TechArticle", "ListItem", "SearchAction", "EntryPoint",
                    "ImageObject"}
DANGLING = {"a", "an", "the", "of", "to", "and", "or", "with", "as", "in", "on", "for", "by", "at", "from", "that", "is"}
VERIFY = {"google_site_verification": "google-site-verification", "bing_site_verification": "msvalidate.01"}
VERIFY_VALUE = re.compile(r"^[A-Za-z0-9_-]{10,100}$")


# ── titles ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def clean_name(name: str) -> str:
    """A page's name for a title: a chapter's number is left out (it stays in the sidebar and the headings)."""
    return re.sub(r"^\d+[a-z]?\.\s*", "", name).strip()


def title_of(name: str, home: bool = False) -> str:
    if home:
        return HOME_TITLE
    name = clean_name(name)
    full = f"{name} · {SITE_NAME}"
    return full if len(full) <= MAX_TITLE else name


def title_problems(titles: dict[str, str]) -> tuple[list[str], list[str]]:
    """(failures, warnings) for {page: title}: a duplicate, a leading digit or more than 90 characters fails; 66 to 90 warns."""
    bad, warn, seen = [], [], {}
    for page, t in sorted(titles.items()):
        if t[:1].isdigit():
            bad.append(f"{page}: the title starts with a digit: {t}")
        if len(t) > FAIL_TITLE_OVER:
            bad.append(f"{page}: the title is {len(t)} characters (at most {FAIL_TITLE_OVER}): {t}")
        elif len(t) > WARN_TITLE_OVER:
            warn.append(f"{page}: the title is {len(t)} characters: {t}")
        if t in seen:
            bad.append(f"{page}: the title is the same as {seen[t]}'s: {t}")
        seen.setdefault(t, page)
    return bad, warn


# ── descriptions ───────────────────────────────────────────────────────────────────────────────────────────────────
def lead(text: str, limit: int = 900) -> str:
    """The plain words of a kit page's first prose paragraphs after its title: the source of its description. Code blocks are
    left out, and the sentence that ends in a colon (it introduces a list) is dropped."""
    text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.S | re.M)
    out = []
    for para in text.split("\n\n")[1:]:
        p = para.strip()
        if not p or p.startswith(("!", "*", "#", "|", "-", "`", ">", "{", "[", "<", "---")) or re.match(r"\d+\.", p):
            continue
        p = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", p.replace("\n", " "))
        p = re.sub(r"\s+", " ", re.sub(r"[`*]|(?<!\w)_|_(?!\w)", "", p)).strip()
        intro = p.endswith(":")
        if intro:
            p = re.sub(r"[^.!?]*:$", "", p).strip()
        if p:
            out.append(p)
        if sum(map(len, out)) >= limit:
            break
    return " ".join(out)


def fit(text: str, kind: str = "page") -> str:
    """A description of 120 to 160 characters from `text`: its first sentences joined until they are long enough and cut at a
    sentence end; a long first sentence is cut at a word; a text that says too little gets the sentence for its kind (or a
    shorter or longer tail, whichever brings it into the bounds)."""
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text) if text else []
    acc = ""
    for s in sentences:
        cand = f"{acc} {s}".strip()
        if len(cand) > MAX_DESC:
            break
        acc = cand
        if len(acc) >= MIN_DESC:
            return acc
    if len(text) >= MIN_DESC:                                        # the next sentence overflows: cut at a clause, else at a word
        window = text[:MAX_DESC - 1]
        clause = max(window.rfind(sep) for sep in ("; ", ", ", ": ", " — "))
        tries = ([window[:clause]] if clause >= MIN_DESC - 1 else []) + [window.rsplit(" ", 1)[0], window]
        for cut in tries:
            for opener, closer in (("(", ")"), ('"', '"')):            # a cut must not leave a bracket or a quotation open
                if (cut.count(opener) > cut.count(closer)) if opener == "(" else cut.count('"') % 2:
                    cut = cut[:cut.rfind(opener)].rstrip()
            while (last := cut.rsplit(" ", 1)[-1].lower()) in DANGLING or (last.endswith("ly") and len(last) > 4):
                cut = cut[: -len(last)].rstrip()
            cut = cut.rstrip(",;:—- .")
            if len(cut) + 1 >= MIN_DESC:
                return cut + "…"
        return tries[-1].rstrip(",;:—- .") + "…"
    kind_sentence = KIND_SENTENCE.get(kind, KIND_SENTENCE["page"])
    for tail in (kind_sentence, f"{kind_sentence} Built from the partner kit.", "On iVendNext Developers.", "iVendNext Developers."):
        if MIN_DESC <= len(f"{acc} {tail}".strip()) <= MAX_DESC:
            return f"{acc} {tail}".strip()
    return f"{acc} {kind_sentence}".strip()                          # none fits: the build asks for a hand-written one


def desc_problems(descs: dict[str, str]) -> list[str]:
    bad, seen = [], {}
    for page, d in sorted(descs.items()):
        if not d:
            bad.append(f"{page}: no description")
        elif not MIN_DESC <= len(d) <= MAX_DESC:
            bad.append(f"{page}: the description is {len(d)} characters (need {MIN_DESC} to {MAX_DESC}); write one in site/seo.json: {d}")
        if d and d in seen:
            bad.append(f"{page}: the description is the same as {seen[d]}'s")
        seen.setdefault(d, page)
    return bad


# ── site/seo.json ──────────────────────────────────────────────────────────────────────────────────────────────────
def load(path: pathlib.Path) -> tuple[dict, list[str]]:
    """The hand-written descriptions and the verification values. Returns (data, errors)."""
    errors: list[str] = []
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        return {"descriptions": {}}, [f"{path.name}: cannot be read: {e}"]
    data.setdefault("descriptions", {})
    for key in VERIFY:
        v = data.get(key, "")
        if v and not VERIFY_VALUE.match(str(v)):
            errors.append(f"{path.name}: {key} is not a verification value (letters, digits, - and _ only)")
    return data, errors


# ── breadcrumbs and structured data ────────────────────────────────────────────────────────────────────────────────
def canonical(out: str) -> str:
    path = "" if out == "index.html" else out.removesuffix("index.html")
    return f"https://{DOMAIN}/{path}"


@dataclass
class PageMeta:
    """What a page tells a search engine and a link preview."""
    name: str                                         # the page's name (its title without the site name)
    desc: str
    kind: str = "page"                                # description kind: guide, recipe, sample, card, needs, feedback, page
    image: str = "home"                               # one of OG_KINDS
    trail: list = field(default_factory=list)         # [(name, out)] from below Home to this page
    modified: str = ""                                # YYYY-MM-DD, or "" (none known: none printed)
    home: bool = False


def crumbs_html(trail: list, up: str) -> str:
    """The visible breadcrumb line: the markup's names and addresses are exactly these."""
    if not trail:
        return ""
    items = [("Home", "index.html")] + list(trail)
    li = "".join(f'<li><a href="{up}{out}">{html.escape(n)}</a></li>' for n, out in items[:-1])
    li += f'<li aria-current="page">{html.escape(items[-1][0])}</li>'
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{li}</ol></nav>'


def organization() -> dict:
    return {"@type": "Organization", "@id": CORP + "#organization", "name": "iVendNext", "url": CORP,
            "logo": f"https://{DOMAIN}/assets/logo.svg"}


def jsonld(meta: PageMeta, out: str) -> str:
    """The page's one JSON-LD block, or "" for a page that has nothing to state."""
    graph: list[dict] = []
    if meta.home:
        graph += [organization(),
                  {"@type": "WebSite", "@id": f"https://{DOMAIN}/#website", "url": f"https://{DOMAIN}/", "name": SITE_NAME,
                   "description": meta.desc, "publisher": {"@id": CORP + "#organization"},
                   "potentialAction": {"@type": "SearchAction",
                                       "target": {"@type": "EntryPoint", "urlTemplate": f"https://{DOMAIN}/search.html?q={{search_term_string}}"},
                                       "query-input": "required name=search_term_string"}}]
    elif meta.trail:
        items = [("Home", "index.html")] + list(meta.trail)
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": canonical(o)} for i, (n, o) in enumerate(items, 1)]})
    list_page = out.endswith("index.html") and out.count("/") <= 1             # guide/index.html, recipes/index.html, samples/index.html
    if meta.kind in TECH_KINDS and not meta.home and meta.trail and not list_page:
        art = {"@type": "TechArticle", "headline": clean_name(meta.name)[:110], "description": meta.desc,
               "mainEntityOfPage": canonical(out), "inLanguage": "en", "image": f"https://{DOMAIN}/assets/og/{meta.image}.png",
               "publisher": organization()}
        if meta.modified:
            art["dateModified"] = meta.modified
        graph.append(art)
    if not graph:
        return ""
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return '<script type="application/ld+json">\n' + data.replace("<", "\\u003c") + "\n</script>"


def head_tags(meta: PageMeta, out: str, title: str, verify: dict | None = None) -> str:
    """The description, canonical address, Open Graph and Twitter tags, the JSON-LD block and (home page only) the
    verification tags that are set."""
    e = lambda s: html.escape(s, quote=True)
    url = canonical(out)
    tags = [f'<meta name="description" content="{e(meta.desc)}">', f'<link rel="canonical" href="{url}">',
            f'<meta property="og:site_name" content="{SITE_NAME}">', '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{e(title)}">', f'<meta property="og:description" content="{e(meta.desc)}">',
            f'<meta property="og:url" content="{url}">',
            f'<meta property="og:image" content="https://{DOMAIN}/assets/og/{meta.image}.png">',
            '<meta property="og:image:type" content="image/png">',
            f'<meta property="og:image:width" content="{OG_SIZE[0]}">', f'<meta property="og:image:height" content="{OG_SIZE[1]}">',
            f'<meta property="og:image:alt" content="{e(OG_ALT[meta.image])}">',
            '<meta name="twitter:card" content="summary_large_image">']
    if meta.home:
        for key, name in VERIFY.items():
            if (verify or {}).get(key):
                tags.append(f'<meta name="{name}" content="{e(str(verify[key]))}">')
    ld = jsonld(meta, out)
    return "\n".join(tags + ([ld] if ld else []))


def ld_problems(text: str, locs: set[str]) -> list[str]:
    """What is wrong with a page's JSON-LD: a block that is not JSON, a type off the allowed list, a breadcrumb that names a
    page that is not on the site, or a breadcrumb whose names are not the ones the page shows."""
    bad = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
    for raw in blocks:
        try:
            data = json.loads(raw)
        except ValueError as e:
            bad.append(f"a JSON-LD block is not JSON: {e}")
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else []
        stack = list(nodes)
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack += n
            elif isinstance(n, dict):
                if "@type" in n and n["@type"] not in ALLOWED_LD_TYPES:
                    bad.append(f"JSON-LD type {n['@type']} is not allowed (no FAQ or HowTo markup)")
                stack += [v for v in n.values() if isinstance(v, (dict, list))]
        for n in nodes:
            if isinstance(n, dict) and n.get("@type") == "BreadcrumbList":
                nav = re.search(r'<nav class="crumbs".*?</nav>', text, re.S)
                shown = [html.unescape(s) for s in re.findall(r"<li[^>]*>(?:<a [^>]*>)?([^<]+)", nav.group() if nav else "")]
                names = [i["name"] for i in n["itemListElement"]]
                if shown != names:
                    bad.append(f"the breadcrumb markup {names} is not the line the page shows {shown}")
                for i in n["itemListElement"]:
                    if i["item"] not in locs:
                        bad.append(f"the breadcrumb names {i['item']}, which is not a page of the site")
    return bad


# ── images ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def image_size(path: pathlib.Path) -> tuple[int, int] | None:
    """The width and height of a PNG or GIF from its header, so a page can reserve the room before the file arrives."""
    import struct
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    return None


# ── dates ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def git_dates(root: pathlib.Path) -> dict[str, str] | None:
    """{file: date of its last commit} for the whole history, or None when the history is not whole (a shallow clone dates
    every file to its newest commit, which would be a date that is not true) or git cannot be read."""
    def run(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None
    if (run("rev-parse", "--is-shallow-repository") or "").strip() != "false":
        return None
    log = run("log", "--format=@%cs", "--name-only", "--no-renames")
    if not log:
        return None
    dates: dict[str, str] = {}
    day = ""
    for line in log.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line.strip() and day:
            dates.setdefault(line.strip(), day)                       # newest first: the first sight is the last change
    return dates


def newest(dates: dict[str, str] | None, sources: list) -> str:
    """The newest last-commit date among a page's sources. A source is a file, a folder ("needs/stock/": any file ever under it,
    a deleted one too, so a page that lists a folder is dated by a removal as well as an edit) or (folder, suffix)."""
    if not dates:
        return ""
    got = []
    for src in sources:
        prefix, suffix = (src, "") if isinstance(src, str) else src
        if isinstance(src, str) and not src.endswith("/"):
            got += [dates[src]] if src in dates else []
        else:
            got += [d for f, d in dates.items() if f.startswith(prefix) and f.endswith(suffix)]
    return max(got) if got else ""


def sitemap(urls: dict[str, str]) -> str:
    """{address: lastmod or ""} to sitemap.xml; a page with no date gets no lastmod."""
    rows = "".join(f"<url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>\n" for u, d in sorted(urls.items()))
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n"


# ── llms.txt ───────────────────────────────────────────────────────────────────────────────────────────────────────
LLMS_INTRO = ("The iVendNext Developers site is the guide, recipes, samples and needs catalogue for anyone who builds for an "
              "iVendNext customer: custom retail POS apps, integrations and extensions, built beside iVendNext without changing it. "
              "Every page is built from the partner kit's own files.")


def llms_txt(sections: list[tuple[str, list[tuple[str, str, str]]]]) -> str:
    """[(section, [(title, address, one line)])] to /llms.txt."""
    out = [f"# {SITE_NAME}", "", f"> {LLMS_INTRO}", ""]
    for head, rows in sections:
        out += [f"## {head}", ""] + [f"- [{t}]({u}): {d}" for t, u, d in rows] + [""]
    return "\n".join(out)


# ── redirects ──────────────────────────────────────────────────────────────────────────────────────────────────────
def read_redirects(path: pathlib.Path) -> list[tuple[str, str]]:
    pairs = []
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                parts = line.split()
                pairs.append((parts[0].lstrip("/"), parts[1].lstrip("/") if len(parts) == 2 else ""))
    return pairs


def redirect_stub(old: str, new: str) -> str:
    """GitHub Pages cannot send a 301: a moved page is a small page that names the new address as its canonical, refreshes to it
    and asks not to be indexed."""
    rel = posixpath.relpath(new, posixpath.dirname(old) or ".")
    to = canonical(new)
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>This page has moved · {SITE_NAME}</title>\n<meta name="robots" content="noindex">\n'
            f'<link rel="canonical" href="{to}">\n<meta http-equiv="refresh" content="0; url={rel}">\n</head>\n<body>\n'
            f'<p>This page has moved to <a href="{rel}">{to}</a>.</p>\n</body>\n</html>\n')
