#!/usr/bin/env python3
"""site/check_links.py — the link check over the BUILT site. Exit 1 on any finding.

    python3 site/check_links.py [SITE_DIR]        # default: site/_out

Fails on: an internal link, image or stylesheet that does not resolve to a file in the built site · a #fragment that is not
an id on its target page · the same id twice on one page · a script, stylesheet, font or image from a host that is not in
ALLOWED_HOSTS (a script is our own file or comes from a listed host) · an inline script, an inline event handler (on…=) or a
javascript: address (a data block such as application/ld+json is not a script) · in an SVG file, a script (any prefix), an entity
declaration or an xml-stylesheet instruction · a page-like file that is not .html · a link to a repository of the org on neither
of its two lists, or to a private one from a page that does not say so (PRIVATE_REPOS). Every way a page can fetch a file is read: href and
src, each candidate of a srcset or imagesrcset, a ping, a url() in a style attribute or a <style> block, an SVG href, and every url() and @import of every
stylesheet and SVG file in the site (comments stripped, any case); a local one must resolve to a file in the built site (a
font named by the stylesheet included). Links to other hosts are not followed. Not read (the site writes none of them): a
bare string in image-set(), a <meta http-equiv="refresh">, CSS escapes inside a URL. Limit: pages are read with Python's HTML
parser, which splits a few odd nestings (a tag inside an attribute value or a comment) differently from a browser, and CI's
Python patch level decides which; the content policy every page carries (build.py) is the backstop for those.
"""
from __future__ import annotations

import pathlib
import posixpath
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit

# Hosts the site may fetch a script, stylesheet, font or image from, bare host names, each with the reason.
# Added by CitiXsys, never by a build session on its own. build.py turns this same list into the content policy
# every page carries, so the browser enforces what this check reads. A listed host may serve a script, a beacon (connect),
# an image, a stylesheet or a font.
#   stats.ivendnext.com: the site's visit counter (cookie-less, on our own host, decided 2026-10-16). The site
#   only ever sends it small reports (site/assets-src/analytics.js); it is named by the page's ivn-analytics meta tag, which
#   build.py writes from ANALYTICS_HOST. Google Analytics, if marketing adds it, is one more line here, with its reason.
ANALYTICS_HOST = "stats.ivendnext.com"
ALLOWED_HOSTS: tuple[str, ...] = (ANALYTICS_HOST,)
# The org's repositories a page may link to. A private one answers GitHub's "page not found" to anyone who may not read it,
# so a page that links one must say so: it carries PRIVATE_CLAUSE, which build.py's MEMBERS_ONLY and NOT_OPEN_YET and the
# feedback page's own sentence share. A link to an org repository on neither list fails. This check follows no outside link,
# so whether each repository is in fact private is read by the live crawl after a deploy. Limit: it reads github.com
# addresses only (the site writes no raw.githubusercontent.com or api.github.com link), and the clause once per page.
ORG_PATH = "/ivendnext-developers/"
PRIVATE_REPOS = ("partner-feedback", "quick-commerce-hub", "3pl-shipping")
PUBLIC_REPOS = ("partner-kit", ".github")
PRIVATE_CLAUSE = "page not found"
DATA_SCRIPT_TYPES = {"application/ld+json", "application/json"}      # a data block is read, never run
URL_ATTRS = ("href", "src", "data", "poster", "action", "formaction")   # matched on the name after any xlink:-style prefix
FETCHES = {"script", "link", "img", "source", "iframe", "image", "use", "feimage", "srcset", "style", "embed", "object", "video", "audio", "track", "input", "ping"}
CSS_URL = re.compile(r"""@import\s*(?:url\()?\s*["']?([^"')\s;]+)|url\(\s*["']?([^"')]+?)["']?\s*\)""", re.I)
SVG_FETCH = re.compile(r"""<(?:[\w.-]+:)?(?:image|use|feimage|script|style)\b[^>]*?\s(?:[\w.-]+:)?href\s*=\s*["']([^"']+)""", re.I)   # an SVG <a> is a link, not a fetch
SVG_HAZARD = re.compile(r"<(?:[\w.-]+:)?script\b|<!ENTITY\b|<\?xml-stylesheet\b", re.I)


def norm(url: str) -> str:
    """The address as a browser reads it: leading and inner whitespace and control characters dropped, a backslash a slash."""
    return re.sub(r"[\x00-\x20]", "", url).replace("\\", "/")


def is_external(url: str) -> bool:
    return bool(re.match(r"^([a-z][a-z0-9+.-]*:|//)", norm(url), re.I))


def first(attrs) -> dict:
    """The attributes as a browser keeps them: when one is written twice, the first wins."""
    d: dict = {}
    for k, v in attrs:
        d.setdefault(k, v)
    return d


def allowed_host(url: str) -> bool:
    """True if `url` is https (or protocol-relative), on port 443, and its host is on ALLOWED_HOSTS (the content policy's rule)."""
    try:
        parts = urlsplit(norm(url))
        port = parts.port
    except ValueError:
        return False
    return parts.scheme in ("https", "") and port in (None, 443) and (parts.hostname or "").lower() in {h.lower() for h in ALLOWED_HOSTS}


def host_of(url: str) -> str:
    try:
        return urlsplit(norm(url)).hostname or url[:40]
    except ValueError:
        return url[:40]


def org_repo(url: str) -> str | None:
    """The org repository a GitHub address points into, lower case and without .git, or None."""
    try:
        parts = urlsplit(norm(url))
    except ValueError:
        return None
    if (parts.hostname or "").lower() not in ("github.com", "www.github.com") or not parts.path.lower().startswith(ORG_PATH):
        return None
    repo = parts.path[len(ORG_PATH):].split("/")[0].lower().removesuffix(".git")
    return repo or None


def css_urls(text: str) -> list[str]:            # every url() and @import target in a piece of CSS, comments ignored
    return [a or b for a, b in CSS_URL.findall(re.sub(r"/\*.*?\*/", "", text, flags=re.S))]


class Hazards(HTMLParser):
    """Reads a page or an SVG for a way to run script inline: a <script> with a body (other than a data block), an on…=
    attribute, a javascript: address, an iframe srcdoc."""
    def __init__(self):
        super().__init__()
        self.hazards: list[str] = []
        self.script_type: str | None = None                   # set while inside a <script> that has no src
        self.script_body = ""

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in first(attrs).items()}
        for k, v in ((k, v or "") for k, v in attrs):                   # every copy of an attribute, not only the one a browser keeps
            if len(k) > 2 and k.startswith("on"):
                self.hazards.append(f"<{tag} {k}=…> is an inline event handler; attach it from a script file of this site")
            elif k == "srcdoc":
                self.hazards.append(f"<{tag} srcdoc=…> is inline markup that can hold a script; use a file of this site")
            elif k.rsplit(":", 1)[-1] in URL_ATTRS and norm(v).lower().startswith("javascript:"):
                self.hazards.append(f"<{tag} {k}=javascript:…> runs script from an address; use a button and a script file")
        if tag in ("set", "animate") and "href" in a.get("attributename", "").lower():
            self.hazards.append(f"<{tag}> sets an href while the page runs; write the address in the markup")
        if tag == "script" and not a.get("src"):
            self.script_type, self.script_body = a.get("type", "").split(";")[0].strip().lower(), ""

    def handle_data(self, data):
        if self.script_type is not None:
            self.script_body += data

    def handle_endtag(self, tag):
        if tag == "script" and self.script_type is not None:
            if self.script_body.strip() and self.script_type not in DATA_SCRIPT_TYPES:
                self.hazards.append("an inline script; move it to a file of this site (a type=\"application/ld+json\" data block is fine)")
            self.script_type = None


class Page(Hazards):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []                 # (kind, url)
        self.text: list[str] = []                             # the page's words, for PRIVATE_CLAUSE
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        a = first(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        self.in_style = tag == "style"
        for key in ("href", "src", "xlink:href", "data", "poster"):
            if tag == "link" and a.get("rel") == "canonical":      # a statement about this page's own address, not a fetch
                continue
            if a.get(key) is not None:
                self.refs.append((tag, a[key]))
        for key in ("srcset", "imagesrcset"):
            if a.get(key):
                self.refs += [("srcset", c.split()[0]) for c in a[key].split(",") if c.strip()]
        self.refs += [("ping", u) for u in (a.get("ping") or "").split()]
        if a.get("style"):
            self.refs += [("style", u) for u in css_urls(a["style"])]

    def handle_data(self, data):
        super().handle_data(data)
        self.text.append(data)
        if self.in_style:
            self.refs += [("style", u) for u in css_urls(data)]

    def handle_endtag(self, tag):
        super().handle_endtag(tag)
        if tag == "style":
            self.in_style = False


def local(root: pathlib.Path, base: str, url: str) -> str | None:
    """The built-site path a local URL written in file `base` points at, or None if no file is there."""
    path = url.partition("#")[0].split("?")[0]
    if not path:
        return base
    target = posixpath.normpath(path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(base), path))
    if (root / target).is_dir():
        target = posixpath.join(target, "index.html")
    return target if (root / target).is_file() else None


def check(root: pathlib.Path) -> list[str]:
    pages: dict[str, Page] = {}
    for f in sorted(root.rglob("*.html")):
        p = Page()
        p.feed(f.read_text("utf-8"))
        pages[f.relative_to(root).as_posix()] = p
    bad: list[str] = []
    files = sorted(root.rglob("*.css")) + sorted(root.rglob("*.svg"))   # a font or image a stylesheet or SVG fetches is a fetch too
    for f in files:
        name, text = f.relative_to(root).as_posix(), f.read_text("utf-8")
        urls = css_urls(text) + (SVG_FETCH.findall(text) if f.suffix == ".svg" else [])
        if f.suffix == ".svg":
            svg = Hazards()
            svg.feed(text)
            bad += [f"{name}: {h}" for h in svg.hazards]
            bad += [f"{name}: a script, an entity declaration or an xml-stylesheet instruction; an SVG file carries none of these"
                    for _ in SVG_HAZARD.findall(text)[:1]]
        for url in urls:
            if url.startswith("data:") or url.startswith("#"):
                continue
            if is_external(url):
                if not allowed_host(url):
                    bad.append(f"{name}: fetches {url[:60]} from another host ({host_of(url)} is not in ALLOWED_HOSTS)")
            elif local(root, name, url) is None:
                bad.append(f"{name}: url {url} does not resolve to a file in the built site")
    bad += [f"{f.relative_to(root).as_posix()}: a page-like file the check does not read; the site ships .html only"
            for f in sorted(root.rglob("*")) if f.suffix.lower() in (".htm", ".xhtml", ".xht", ".html") and f.suffix != ".html"]
    for name, p in pages.items():
        dup = {i for i in p.ids if p.ids.count(i) > 1}
        bad += [f"{name}: the id #{i} appears twice" for i in sorted(dup)]
        bad += [f"{name}: {h}" for h in p.hazards]
        says_private = PRIVATE_CLAUSE in re.sub(r"\s+", " ", " ".join(p.text)).lower()
        for kind, url in p.refs:
            repo = org_repo(url) if is_external(url) else None
            if repo in PRIVATE_REPOS and not says_private:
                bad.append(f"{name}: links the private repository {repo} but does not say so (build.py MEMBERS_ONLY or NOT_OPEN_YET: "
                           f"\"{PRIVATE_CLAUSE}\" beside it)")
            elif repo and repo not in PRIVATE_REPOS + PUBLIC_REPOS:
                bad.append(f"{name}: links ivendnext-developers/{repo}, which is on neither list in check_links.py "
                           f"(PRIVATE_REPOS, PUBLIC_REPOS)")
            if is_external(url):
                if kind == "base":                              # a <base> from elsewhere re-aims every relative script and file
                    bad.append(f"{name}: <base href={url[:60]}> points the page at another host")
                elif kind in FETCHES and not allowed_host(url):
                    bad.append(f"{name}: <{kind}> loads {url} from another host ({host_of(url)} is not in ALLOWED_HOSTS: "
                               f"serve it from this site, or add the host to ALLOWED_HOSTS in check_links.py with a reason)")
            elif url and not url.startswith("data:"):
                frag = url.partition("#")[2]
                target = local(root, name, url)
                if target is None:
                    bad.append(f"{name}: broken link {url}")
                    continue
                if frag and target.endswith(".html") and frag not in pages[target].ids:
                    bad.append(f"{name}: {url} — no #{frag} on {target}")
    return bad


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "_out").resolve()
    bad = check(root)
    n = len(list(root.rglob("*.html")))
    if bad:
        print(f"LINK CHECK RED: {len(bad)} finding(s) in {n} pages")
        print("\n".join("  " + b for b in bad[:60]))
        return 1
    print(f"LINK CHECK GREEN: {n} pages, every internal link, image and #fragment resolves; every script is ours or from a listed host; no inline script or handler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
