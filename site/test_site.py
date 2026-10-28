#!/usr/bin/env python3
"""site/test_site.py — the site build and its link check, each shown able to fail.   python3 site/test_site.py"""
import pathlib
import posixpath
import re
import shutil
import sys
import tempfile
import importlib.util
import json
import unittest
from unittest import mock
from html import unescape as html_unescape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build        # noqa: E402
import seo          # noqa: E402
import check_links  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).parent / "pdf"))
import build_pdfs   # noqa: E402  (the branded PDFs, built after the site as the Site workflow does; needs Chrome)

_spec = importlib.util.spec_from_file_location("issue_forms", build.ROOT / ".github" / "scripts" / "issue_forms.py")
issue_forms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(issue_forms)
PARTNER_FORM = "https://www.ivendnext.com/partners/apply/"
# Calls with no iVendNext name yet: the sign-in addresses (the standard discovery document lists them anyway) and
# server-side code that runs inside the shop. Every other call has one in ivendnext_mpos.api.v1.
UPSTREAM_KEPT = ("frappe.integrations.oauth2.", "frappe.get_doc(")


def upstream_calls(text: str) -> list[str]:
    """The upstream package paths a page names, less the kept ones."""
    hits = re.finditer(r"\b(?:frappe|erpnext)\.[A-Za-z_][\w.]*\(?", text)
    return [m.group().rstrip("(") for m in hits if not m.group().startswith(UPSTREAM_KEPT)]


DOWNLOAD = re.compile(r"https://developer\.ivendnext\.com/(downloads/[^\"'\s)<>#?]+)")


def missing_downloads(out: pathlib.Path) -> list[str]:
    """The absolute download addresses in the built pages that name no file in downloads/ (check_links.py does not follow
    absolute addresses, and these are absolute so that they work on GitHub too)."""
    return sorted({f"{page}: {m.group(0)}" for page, text in page_texts(out, only_indexable=False).items()
                   for m in DOWNLOAD.finditer(text) if not (out / m.group(1)).is_file()})


def indexable(text: str) -> bool:
    """A page search engines may index: every page but one that says noindex (the 404 and search.html; later lanes add their own)."""
    return 'name="robots" content="noindex"' not in text


# The vendored search library (site/assets-src/vendor/minisearch-7.2.0/, SOURCE.txt beside it): each file's sha256. A change to
# any of them turns test_the_vendored_search_library_is_the_pinned_one red; an upgrade is a new folder and new lines here.
VENDOR = {"minisearch-7.2.0/index.js": "03c27931eb603af1d3358579e9885eafdb6a2f5fa9929557b3e77d7e99d06d03",
          "minisearch-7.2.0/index.js.map": "4bf7e52bd41838937a53151140594816afdcc913b2fd8348f9ef44668beeda41",
          "minisearch-7.2.0/LICENSE.txt": "70d37354d6395629fb99edb28cb37a5d356ffa24a48cd02a5def5b83a300a899"}


def vendor_drift(folder: pathlib.Path) -> list[str]:
    import hashlib
    return [name for name, digest in VENDOR.items()
            if not (folder / name).is_file() or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest]


def catalogue_cards() -> list:
    sys.path.insert(0, str(build.ROOT / "tools" / "needs"))
    import needs
    return needs.load(build.ROOT)


def catalogue_backlinks() -> dict:
    sys.path.insert(0, str(build.ROOT / "tools" / "needs"))
    import needs
    return needs.backlinks(needs.load(build.ROOT))


def page_texts(out: pathlib.Path, only_indexable: bool = True) -> dict[str, str]:
    """{address from the site root: html} of the built pages (the redirect stubs and the noindex pages left out by default)."""
    pages = {f.relative_to(out).as_posix(): f.read_text("utf-8") for f in sorted(out.rglob("*.html"))}
    return {k: v for k, v in pages.items() if indexable(v)} if only_indexable else pages


def og_problems(images: dict[str, pathlib.Path]) -> list[str]:
    """What is wrong with the preview images {kind: file}: missing, not a PNG of 1200 x 630, or over 150 kB."""
    bad = []
    for kind, f in images.items():
        if not f.is_file():
            bad.append(f"{kind}: {f.name} is missing")
        elif seo.image_size(f) != seo.OG_SIZE:
            bad.append(f"{kind}: {f.name} is {seo.image_size(f)}, not {seo.OG_SIZE}")
        elif f.stat().st_size > 150_000:
            bad.append(f"{kind}: {f.name} is {f.stat().st_size} bytes (at most 150 kB)")
    return bad


def lastmod_problems(sitemap_xml: str, today: str) -> list[str]:
    """A lastmod that is not a date, or that is after `today`."""
    bad = []
    for d in re.findall(r"<lastmod>([^<]*)</lastmod>", sitemap_xml):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            bad.append(f"lastmod {d} is not a date")
        elif d > today:
            bad.append(f"lastmod {d} is in the future")
    return bad


def unreachable(root: pathlib.Path, targets: list[str], clicks: int = 3) -> list[str]:
    """The target pages a visitor cannot reach from the home page in at most `clicks` clicks on the built site's own links."""
    seen, frontier = {"index.html"}, ["index.html"]
    for _ in range(clicks):
        nxt = []
        for page in frontier:
            p = check_links.Page()
            p.feed((root / page).read_text("utf-8"))
            for tag, url in p.refs:
                if tag != "a":
                    continue
                target = check_links.local(root, page, url) if not re.match(r"^([a-z][a-z0-9+.-]*:|//)", url, re.I) else None
                if target and target.endswith(".html") and target not in seen:
                    seen.add(target)
                    nxt.append(target)
        frontier = nxt
    return [t for t in targets if t not in seen]


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "out"
        assert build.build(cls.out) == 0
        assert build_pdfs.build_pdfs(cls.out) == 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def planted(self, name: str, edit, files: dict | None = None) -> list[str]:
        copy = self.tmp / name
        shutil.copytree(self.out, copy)
        f = copy / "guide/01_welcome.html"
        f.write_text(edit(f.read_text("utf-8")), "utf-8")
        for rel, text in (files or {}).items():
            (copy / rel).write_text(text, "utf-8")
        return check_links.check(copy)

    def in_head(self, name: str, tag: str, files: dict | None = None, hosts: tuple = ()) -> list[str]:
        with mock.patch.object(check_links, "ALLOWED_HOSTS", hosts):
            return self.planted(name, lambda h: h.replace("</head>", tag + "</head>"), files)

    def test_built_site_is_clean(self):
        self.assertEqual(check_links.check(self.out), [])

    # the downloads (row PDFFORM): the blueprint's PDFs and its template
    def test_every_download_address_names_a_built_file_and_a_missing_one_is_red(self):
        self.assertEqual(missing_downloads(self.out), [])
        linked = {m.group(1) for text in page_texts(self.out).values() for m in DOWNLOAD.finditer(text)}
        self.assertEqual(linked, {"downloads/blueprint_form.pdf", "downloads/blueprint_how_to_fill.pdf", "downloads/blueprint_template.md",
                                  "downloads/blueprint_example.pdf", "downloads/blueprint_example.md",
                                  "downloads/ladder_and_four_rules.pdf", "downloads/needs_at_a_glance.pdf",
                                  "downloads/how_ivendnext_apps_work.pdf",
                                  "downloads/how_the_data_travels.pdf"})
        copy = self.tmp / "missing_download"
        shutil.copytree(self.out, copy)
        page = copy / "kit" / "blueprint.html"
        page.write_text(page.read_text("utf-8").replace("downloads/blueprint_form.pdf", "downloads/no_such_form.pdf"), "utf-8")
        self.assertTrue(any("no_such_form.pdf" in m for m in missing_downloads(copy)))

    def test_every_site_address_a_pdf_links_is_a_built_page_or_file(self):
        def missing(page_html: str) -> list[str]:            # the PDFs' links are absolute, so check_links.py cannot follow them
            urls = re.findall(r'href="https://developer\.ivendnext\.com/([^"#?]*)', page_html)
            return [u for u in urls if not (self.out / (u or "index.html")).is_file()] if urls else ["no site address at all"]
        for doc in build_pdfs.DOCS:
            self.assertEqual(missing(build_pdfs.page(doc.title, doc.make([]), doc.cls)), [], doc.name)
        planted = build_pdfs.page("A test", '<a href="https://developer.ivendnext.com/kit/no_such_page.html">gone</a>')
        self.assertEqual(missing(planted), ["kit/no_such_page.html"])

    def test_the_template_is_a_page_of_real_tables_and_a_download_equal_to_the_kit_file(self):
        page = self.html_of("kit/blueprint_template.html")
        self.assertEqual(page.count("<table>"), 6)                  # the fields and (b) to (f)
        self.assertNotIn("<pre", page.split('<main id="main">')[1])
        self.assertEqual((self.out / "downloads" / "blueprint_template.md").read_bytes(), (build.ROOT / "kit/blueprint_template.md").read_bytes())
        blueprint = self.html_of("kit/blueprint.html")
        self.assertIn('href="blueprint_template.html"', blueprint)
        self.assertNotIn("## (b) Fit-gap", blueprint)               # the old code block is gone

    # the blueprint's three pages (row PDFMORE): three labels, and the example held to today's cards
    def test_the_three_blueprint_pages_have_three_sidebar_labels_and_a_duplicate_label_is_red(self):
        side = self.html_of("kit/blueprint_example.html").split('<nav class="side"')[1].split("</nav>")[0]
        labels = re.findall(r'<li><a href="[^"]*kit/blueprint(?:_example|_template)?\.html"[^>]*>([^<]+)</a>', side)
        self.assertEqual(labels, ["The project blueprint", "Blueprint example", "Blueprint template"])
        self.assertEqual(build.label_errors(build.collect()), [])
        pages = build.collect()
        twin = next(p for p in pages if p.src == build.EXAMPLE)
        twin.title = "The project blueprint — a planted twin"
        self.assertEqual(len(build.label_errors(pages)), 1, build.label_errors(pages))

    def test_the_example_is_a_page_and_a_download_and_holds_to_its_cards(self):
        self.assertEqual((self.out / "downloads" / "blueprint_example.md").read_bytes(), (build.ROOT / build.EXAMPLE).read_bytes())
        self.assertNotIn("A filled example", self.html_of("kit/blueprint.html"))          # one home: the old example is gone
        self.assertIn('href="blueprint_example.html"', self.html_of("kit/blueprint_template.html"))
        cards = build.catalogue.load(build.ROOT)
        self.assertEqual(build.example_errors(cards), [])
        rows = [ln for ln in build.section(build.EXAMPLE, "(b) Fit-gap").splitlines() if re.match(r"\| \d+ \|", ln)]
        self.assertTrue(8 <= len(rows) <= 12, len(rows))
        statuses = {ln.split("|")[4].strip() for ln in rows}
        self.assertTrue({"Ready", "Ready, with limits", "Not yet"} <= statuses, statuses)
        self.assertTrue(any("| none |" in ln for ln in rows))

    def test_a_card_that_changes_or_a_row_naming_no_card_fails_the_site_build(self):
        kit = self.planted_kit("example_card", also=("kit",))
        self.assertEqual(self.build_in(kit), 0)
        card = kit / "needs" / "documents" / "gift-receipt.md"
        card.write_text(card.read_text("utf-8").replace("status: ready\n", "status: ready-with-limits\n"), "utf-8")
        real = build.ROOT
        build.ROOT = kit
        try:
            errors = build.example_errors(build.catalogue.load(kit))
        finally:
            build.ROOT = real
        self.assertTrue(any("now says 'Ready, with limits'" in e for e in errors), errors)
        self.assertEqual(self.build_in(kit), 1)
        card.write_text(card.read_text("utf-8").replace("status: ready-with-limits\n", "status: ready\n"), "utf-8")
        example = kit / build.EXAMPLE
        original = example.read_text("utf-8")
        for planted, said in (("| Ready | Configure |", "| Ready | Till key |"),                   # the wrong door
                              ("| Ready | Configure |", "| Ready, mostly | Configure |")):          # not a verdict word
            example.write_text(original.replace(*(planted, said), 1), "utf-8")
            build.ROOT = kit
            try:
                errors = build.example_errors(build.catalogue.load(kit))
            finally:
                build.ROOT = real
            self.assertTrue(any(("does not name" in e) if "Till key" in said else ("is not one of the four" in e) for e in errors), errors)
        example.write_text(original.replace("| gift-receipt |", "| no-such-card |"), "utf-8")
        self.assertEqual(self.build_in(kit), 1)
        build.ROOT = kit
        try:
            self.assertTrue(any("no card has the id 'no-such-card'" in e for e in build.example_errors(build.catalogue.load(kit))))
        finally:
            build.ROOT = real

    def test_needs_at_a_glance_lists_exactly_the_cards_of_catalogue_json(self):
        import json
        ids = [d["id"] for d in json.loads((self.out / "catalogue.json").read_text("utf-8"))]
        rows = re.findall(r'<tr data-id="([^"]*)"', build_pdfs.glance_body([]))
        self.assertEqual(sorted(rows), sorted(ids))
        self.assertEqual(len(rows), len(set(rows)))

    def test_broken_page_link_is_red(self):
        bad = self.planted("a", lambda h: h.replace("</main>", '<a href="no_such_page.html">x</a></main>'))
        self.assertTrue(any("broken link no_such_page.html" in b for b in bad), bad)

    def test_broken_fragment_is_red(self):
        bad = self.planted("b", lambda h: h.replace("</main>", '<a href="02_getting_started.html#no-such-heading">x</a></main>'))
        self.assertTrue(any("no #no-such-heading" in b for b in bad), bad)

    def test_broken_image_is_red(self):
        bad = self.planted("c", lambda h: h.replace("</main>", '<img src="gone.png" alt="">' + "</main>"))
        self.assertTrue(any("broken link gone.png" in b for b in bad), bad)

    def test_a_script_of_ours_is_green_and_a_missing_one_is_red(self):
        self.assertEqual(self.in_head("d1", '<script src="../assets/app.js" defer></script>', {"assets/app.js": "var a = 1;\n"}), [])
        bad = self.in_head("d2", '<script src="../assets/gone.js"></script>')
        self.assertTrue(any("broken link ../assets/gone.js" in b for b in bad), bad)

    def test_a_script_from_an_unlisted_host_is_red_and_from_a_listed_host_green(self):
        tag = '<script src="https://stats.example.com/a.js"></script>'
        bad = self.in_head("d3", tag)
        self.assertTrue(any("<script> loads https://stats.example.com/a.js from another host" in b and "ALLOWED_HOSTS" in b for b in bad), bad)
        self.assertEqual(self.in_head("d4", tag, hosts=("stats.example.com",)), [])
        self.assertEqual(self.in_head("d4b", '<script src="//stats.example.com/a.js"></script>', hosts=("Stats.Example.com",)), [])
        # the same host with another host behind a backslash, userinfo, a scheme-less or an http address is not the listed host
        for n, url in enumerate(("https://evil.example\\@stats.example.com/a.js", "https://stats.example.com@evil.example/a.js",
                                 "http://stats.example.com/a.js", "https://stats.example.com.evil.example/a.js",
                                 "data:text/javascript,alert(1)")):
            bad = self.in_head(f"d5{n}", f'<script src="{url}"></script>', hosts=("stats.example.com",))
            self.assertTrue(any("from another host" in b for b in bad), (url, bad))

    def test_an_inline_script_is_red_and_a_data_block_green(self):
        bad = self.in_head("d6", "<script>document.title = 'x'</script>")
        self.assertTrue(any("an inline script" in b for b in bad), bad)
        data = '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "WebSite"}</script>'
        self.assertEqual(self.in_head("d7", data), [])
        self.assertEqual(self.in_head("d7b", data.replace("ld+json", "JSON; charset=utf-8").replace("application/JSON", "application/json")), [])
        bad = self.in_head("d7c", '<script type="module">import "./a.js"</script>')
        self.assertTrue(any("an inline script" in b for b in bad), bad)

    def test_an_inline_event_handler_is_red(self):
        for n, tag in enumerate(('<a href="#x" onclick="go()">x</a>', '<img src="../assets/logo.svg" alt="" onerror="go()">',
                                 '<body onLoad="go()">'), 1):
            bad = self.planted(f"h{n}", lambda h: h.replace("</main>", tag + "</main>"))
            self.assertTrue(any("is an inline event handler" in b for b in bad), (tag, bad))

    def test_a_stylesheet_from_an_unlisted_host_is_red_and_from_a_listed_host_green(self):
        tag = '<link rel="stylesheet" href="https://cdn.example.com/a.css">'
        bad = self.in_head("s1", tag)
        self.assertTrue(any("<link> loads https://cdn.example.com/a.css from another host" in b for b in bad), bad)
        self.assertEqual(self.in_head("s2", tag, hosts=("cdn.example.com",)), [])

    def test_a_javascript_address_is_red(self):
        for n, href in enumerate(("javascript:go()", " JaVa\tScript:go()", "&#106;avascript:go()")):
            bad = self.planted(f"j{n}", lambda h: h.replace("</main>", f'<a href="{href}">x</a></main>'))
            self.assertTrue(any("javascript:" in b for b in bad), (href, bad))
        bad = self.planted("j9", lambda h: h.replace("</main>", '<iframe srcdoc="<script>1</script>"></iframe></main>'))
        self.assertTrue(any("srcdoc" in b for b in bad), bad)

    def test_a_base_tag_pointing_elsewhere_is_red(self):
        bad = self.in_head("b1", '<base href="https://evil.example/">', hosts=("evil.example",))
        self.assertTrue(any("<base href=" in b for b in bad), bad)

    def test_a_script_or_handler_inside_an_svg_is_red(self):
        clean = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>'
        self.assertEqual(self.planted("v0", lambda h: h, {"assets/x.svg": clean}), [])
        for n, svg in enumerate((clean.replace("<path", "<script>1</script><path"), clean.replace("<path", "<script href=\"a.js\"/><path"),
                                 clean.replace("<svg ", "<svg onload=\"go()\" "), clean.replace("<path", '<a href="javascript:go()"><path')), 1):
            bad = self.planted(f"v{n}", lambda h: h, {"assets/x.svg": svg})
            self.assertTrue(any(b.startswith("assets/x.svg:") and ("script" in b or "event handler" in b) for b in bad), (svg, bad))

    def test_an_svg_cannot_hide_a_script_behind_a_prefix_an_entity_or_a_stylesheet_instruction(self):
        clean = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>'
        for n, svg in enumerate(('<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:script>alert(1)</s:script></s:svg>',
                                 '<!DOCTYPE svg [<!ENTITY s "<script>1</script>">]><svg xmlns="http://www.w3.org/2000/svg">&s;</svg>',
                                 '<?xml-stylesheet type="text/xsl" href="x.xsl"?>' + clean,
                                 clean.replace("<path", '<set attributeName="href" to="javascript:go()"/><path'),
                                 clean.replace("<path", '<q:a q:href="javascript:go()" xmlns:q="http://www.w3.org/1999/xlink"><path'),
                                 clean.replace("<path", '<q:image q:href="https://evil.example/x.png" xmlns:q="http://www.w3.org/1999/xlink"/><path')), 1):
            bad = self.planted(f"p{n}", lambda h: h, {"assets/x.svg": svg})
            self.assertTrue(any(b.startswith("assets/x.svg:") for b in bad), (svg, bad))

    def test_an_address_a_browser_reads_as_another_host_is_red_however_it_is_written(self):
        for n, url in enumerate(("/\\evil.example/../assets/favicon.svg", " https://evil.example/../../../assets/favicon.svg",
                                 " //evil.example/../../../assets/favicon.svg", "ht\ttps://evil.example/x.png")):
            bad = self.planted(f"w{n}", lambda h: h.replace("</main>", f'<img src="{url}" alt=""></main>'))
            self.assertTrue(any("from another host" in b for b in bad), (url, bad))
        # a listed host on another port is not the host the policy lists
        bad = self.in_head("w9", '<script src="https://stats.example.com:8443/a.js"></script>', hosts=("stats.example.com",))
        self.assertTrue(any("from another host" in b for b in bad), bad)
        self.assertEqual(self.in_head("w9b", '<script src="https://stats.example.com:443/a.js"></script>', hosts=("stats.example.com",)), [])

    def test_a_repeated_attribute_is_read_as_a_browser_reads_it(self):
        for n, tag in enumerate(('<script src="https://evil.example/a.js" src=""></script>', '<img src="https://evil.example/x.png" src="" alt="">',
                                 '<link rel="stylesheet" rel="canonical" href="https://evil.example/a.css">'), 1):
            bad = self.planted(f"r{n}", lambda h: h.replace("</main>", tag + "</main>"))
            self.assertTrue(any("from another host" in b for b in bad), (tag, bad))
        bad = self.planted("r4", lambda h: h.replace("</main>", '<a href="javascript:go()" href="#">x</a></main>'))
        self.assertTrue(any("javascript:" in b for b in bad), bad)

    def test_a_ping_and_an_imagesrcset_are_fetches(self):
        bad = self.planted("q1", lambda h: h.replace("</main>", '<a href="#" ping="https://evil.example/b">x</a></main>'))
        self.assertTrue(any("<ping> loads https://evil.example/b" in b for b in bad), bad)
        bad = self.in_head("q2", '<link rel="preload" as="image" imagesrcset="https://evil.example/x.png 1x" href="../assets/favicon.svg">')
        self.assertTrue(any("<srcset> loads https://evil.example/x.png" in b for b in bad), bad)

    def test_a_page_with_another_extension_is_red(self):
        for n, name in enumerate(("x.htm", "y.xhtml", "X.HTML")):
            bad = self.planted(f"x{n}", lambda h: h, {f"assets/{name}": "<script>alert(1)</script>"})
            self.assertTrue(any(b.startswith(f"assets/{name}:") and "page-like" in b for b in bad), (name, bad))

    def test_the_content_policy_is_on_every_page_and_follows_the_list(self):
        tag = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">')
        for f in self.out.rglob("*.html"):
            m = tag.search(f.read_text("utf-8"))
            self.assertTrue(m, f"{f}: no content policy")
            self.assertIn("script-src 'self'", m.group(1))
            if f.relative_to(self.out).as_posix() in build.OWN_POLICY:   # its own, in place of the site's: one address
                self.assertEqual(m.group(1), build.page_policy(), f.name)
                self.assertEqual(re.findall(r"https://[^\s;]+", m.group(1)), [build.HOSTING_API], f.name)
                self.assertEqual(len(tag.findall(f.read_text("utf-8"))), 1, f.name)
                continue
            self.assertEqual(set(re.findall(r"https://[^\s;]+", m.group(1))), {f"https://{h}" for h in check_links.ALLOWED_HOSTS}, f.name)
        with mock.patch.object(check_links, "ALLOWED_HOSTS", ("stats.example.com",)), mock.patch.object(check_links, "ANALYTICS_HOST", "stats.example.com"):
            policy = tag.search(build.shell("T", "<p>x</p>", "x.html", noindex=True)).group(1)
        dirs = dict(d.split(" ", 1) for d in policy.split("; "))
        for d in ("script-src", "connect-src", "img-src", "font-src", "style-src"):
            self.assertIn("https://stats.example.com", dirs[d], d)
        self.assertIn("'unsafe-inline'", dirs["style-src"])
        for d in ("default-src", "object-src", "base-uri", "form-action"):
            self.assertNotIn("stats.example.com", dirs[d], d)
        self.assertEqual((dirs["object-src"], dirs["base-uri"], dirs["form-action"]), ("'none'", "'self'", "'self'"))

    def test_every_page_names_the_counter_loads_analytics_before_search_and_says_so_in_the_footer(self):
        want = f'<meta name="ivn-analytics" content="https://{check_links.ANALYTICS_HOST}">'
        for f in self.out.rglob("*.html"):
            t = f.read_text("utf-8")
            if f.relative_to(self.out).as_posix() in build.OWN_POLICY:   # no counter on the page that holds a sign-in
                self.assertNotIn("ivn-analytics", t, f.name)
                self.assertNotIn("assets/analytics.js", t, f.name)
            else:
                self.assertEqual(t.count(want), 1, f.name)
                self.assertLess(t.index('assets/analytics.js" defer'), t.index('assets/search.js" defer'), f.name)
            self.assertIn("counts visits without cookies or personal data", t, f.name)
            self.assertIn('href="https://ivend.com/privacy-policy/">privacy policy</a>', t, f.name)
            self.assertNotIn("<script>", t.replace('<script type="application/ld+json">', ""), f.name)      # still no inline script

    def test_a_counter_that_is_not_on_the_allowed_list_fails_the_build_and_the_policy_would_block_it(self):
        with mock.patch.object(check_links, "ALLOWED_HOSTS", ()):
            with self.assertRaisesRegex(ValueError, "is not on ALLOWED_HOSTS"):
                build.shell("T", "<p>x</p>", "x.html", noindex=True)
        with mock.patch.object(check_links, "ANALYTICS_HOST", "stats.example.com"):
            with self.assertRaisesRegex(ValueError, "stats.example.com"):
                build.shell("T", "<p>x</p>", "x.html", noindex=True)           # the list holds the real host, not this one

    def test_the_counters_script_ships_unchanged_and_nothing_else_is_fetched_from_it(self):
        self.assertEqual((self.out / "assets/analytics.js").read_bytes(), (build.SITE / "assets-src/analytics.js").read_bytes())
        src = (build.SITE / "assets-src/analytics.js").read_text("utf-8")
        for bad in ("document.cookie", "localStorage", "indexedDB", "navigator.sendBeacon", "XMLHttpRequest", "createElement"):
            self.assertNotIn(bad, src, f"analytics.js must not use {bad}")

    def test_the_real_host_list_holds_bare_host_names(self):
        bare = r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$"
        for h in ("stats.example.com", "www.googletagmanager.com"):
            self.assertRegex(h, bare)
        for h in ("https://stats.example.com", "stats.example.com/a", "*.example.com", "stats.example.com:8443", "a b", "x;y"):
            self.assertNotRegex(h, bare, h)                      # the pattern itself can fail
        for h in check_links.ALLOWED_HOSTS:
            self.assertRegex(h, bare, "ALLOWED_HOSTS takes bare host names, no scheme, path or wildcard")

    def test_search_basics(self):
        import re
        sitemap = (self.out / "sitemap.xml").read_text("utf-8")
        locs = set(re.findall(r"<loc>([^<]+)</loc>", sitemap))
        self.assertIn("https://developer.ivendnext.com/", locs)
        self.assertIn("Sitemap: https://developer.ivendnext.com/sitemap.xml", (self.out / "robots.txt").read_text("utf-8"))
        descs, n = {}, 0
        for f in self.out.rglob("*.html"):
            text = f.read_text("utf-8")
            if not indexable(text):
                if 'http-equiv="refresh"' not in text:                                  # a redirect stub names the new address as its canonical
                    self.assertNotIn('rel="canonical"', text, f.name)
                continue
            n += 1
            canon = re.search(r'<link rel="canonical" href="([^"]+)"', text)
            self.assertTrue(canon and canon.group(1) in locs, f"{f}: canonical missing or not in the sitemap")
            descs.setdefault(re.search(r'<meta name="description" content="([^"]*)"', text).group(1), []).append(f.name)
        self.assertEqual(len(locs), n)                                                    # every indexable page, no other
        self.assertFalse(indexable((self.out / "404.html").read_text("utf-8")))
        dup = {d: n for d, n in descs.items() if len(n) > 1}
        self.assertEqual(dup, {}, "two pages share one description")

    # ── the search (row SITESEARCH) ─────────────────────────────────────────────────────────────────────────────────────
    def test_the_results_page_is_noindex_and_not_in_the_sitemap(self):
        text = (self.out / "search.html").read_text("utf-8")
        self.assertFalse(indexable(text))
        self.assertNotIn("search.html", (self.out / "sitemap.xml").read_text("utf-8"))
        for name in ("area", "door", "status"):
            self.assertIn(f'<select id="f-{name}" name="{name}">', text)
        self.assertIn('<a href="needs/all.html">', text)                               # what to do without script

    def test_every_page_has_the_search_box_and_without_script_it_opens_all_needs(self):
        for f in self.out.rglob("*.html"):
            text = f.read_text("utf-8")
            up = "/" if f.name == "404.html" else "../" * f.relative_to(self.out).as_posix().count("/")
            self.assertIn(f'<form class="site-search" role="search" action="{up}needs/all.html" method="get" data-root="{up}">', text, f.name)
            if f.relative_to(self.out).as_posix() in build.OWN_POLICY:   # the hosting page runs only its own script
                self.assertNotIn("assets/search.js", text, f.name)
                continue
            self.assertIn(f'<script src="{up}assets/search.js" defer></script>', text, f.name)
        self.assertTrue((self.out / "needs/all.html").exists())
        self.assertIn('href="index.html#a-to-z"', (self.out / "needs/all.html").read_text("utf-8"))

    def test_the_vendored_search_library_is_the_pinned_one(self):
        self.assertEqual(vendor_drift(self.out / "assets" / "vendor"), [])
        copy = self.tmp / "vendor"
        shutil.copytree(self.out / "assets" / "vendor", copy)
        lib = copy / "minisearch-7.2.0" / "index.js"
        lib.write_bytes(lib.read_bytes().replace(b"'use strict';", b"'use strict'; window.x = 1;", 1))
        self.assertEqual(vendor_drift(copy), ["minisearch-7.2.0/index.js"])

    def test_the_search_index_holds_every_card_first_and_stays_small(self):
        import json
        data = json.loads((self.out / "search-index.json").read_text("utf-8"))
        cards = build.catalogue.load(build.ROOT)
        self.assertEqual([d["id"] for d in data[:len(cards)]], [f"needs/{c.area}/{c.id}.html" for c in build.by_asks(cards)])
        self.assertTrue(all((self.out / d["u"]).exists() for d in data))
        self.assertTrue({"recipe", "sample", "guide"} <= {d["k"] for d in data})
        self.assertLessEqual((self.out / "search-index.json").stat().st_size, 500 * 1024)

    def test_the_synonym_list_is_whole_and_a_bad_group_is_red(self):
        groups = build.synonyms()
        self.assertGreaterEqual(len(groups), 40)
        self.assertEqual(build.synonym_errors(groups), [])
        self.assertTrue(any("group 2" in e for e in build.synonym_errors([["store", "branch"], ["alone"]])))
        self.assertTrue(any("group 2" in e for e in build.synonym_errors([["store", "branch"], ["till", ""]])))
        self.assertTrue(any("'branch' is in group 1 and group 2" in e for e in build.synonym_errors([["store", "branch"], ["branch", "outlet"]])))

    def test_a_synonym_matches_a_whole_word_or_phrase_and_its_plural(self):
        groups = [["store", "branch"], ["buy now pay later", "bnpl"]]
        self.assertIn("branch", build.expand("A reminder per store", groups))
        self.assertIn("branch", build.expand("Two stores", groups))
        self.assertNotIn("branch", build.expand("A storey building", groups))
        self.assertIn("bnpl", build.expand("Pay with a buy-now-pay-later provider", groups))
        self.assertNotIn("procurement", build.expand("beyond its POS profile", [["purchase order", "po", "procurement"]]))   # no plural on two letters

    def test_an_area_page_groups_its_cards_by_topic(self):
        text = (self.out / "needs/stock/index.html").read_text("utf-8")
        labels = list(build.catalogue.TOPICS["stock"].values())
        for label in labels:
            sid = build.slug(label)
            self.assertIn(f'<h2 id="{sid}">{label}</h2>', text)
            self.assertIn(f'href="#{sid}"', text)
        self.assertEqual([text.index(f'<h2 id="{build.slug(l)}">') for l in labels],
                         sorted(text.index(f'<h2 id="{build.slug(l)}">') for l in labels))
        self.assertLess(text.index(">Counts</h2>"), text.index("count-list-totals.html"))
        self.assertLess(text.index("count-list-totals.html"), text.index(">Alerts and reorder</h2>"))

    def test_popular_cards_come_first_on_their_area_page(self):
        text = (self.out / "needs/till/index.html").read_text("utf-8")
        self.assertLess(text.index("Popular in this area"), text.index(">Manager approvals</h2>"))
        pop = text[text.index("Popular in this area"):text.index(">Manager approvals</h2>")]
        self.assertIn("line-quantity-cap.html", pop)
        self.assertNotIn("Popular in this area", (self.out / "needs/reports/index.html").read_text("utf-8"))   # none marked

    def test_the_catalogue_lists_the_twelve_newest_cards(self):
        text = (self.out / "needs/index.html").read_text("utf-8")
        part = text[text.index('id="new-and-changed"'):text.index('id="popular-needs"')]
        newest = build.newest(build.catalogue.load(build.ROOT))
        self.assertEqual(len(newest), 12)
        self.assertEqual(part.count("<li>"), 12)
        for c in newest:
            self.assertIn(f'href="{c.area}/{c.id}.html"', part)
        dates = [c.checked_on() for c in newest]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_a_card_page_links_its_topic_on_its_area_page(self):
        text = (self.out / "needs/stock/count-list-totals.html").read_text("utf-8")
        self.assertIn('href="index.html#counts">Counts</a>', text)

    def test_a_webfont_in_a_stylesheet_is_red(self):
        copy = self.tmp / "e"
        shutil.copytree(self.out, copy)
        css = copy / "assets/site.css"
        css.write_text('@import url("https://fonts.example.com/inter.css");\n' + css.read_text("utf-8"), "utf-8")
        self.assertTrue(any("another host" in b for b in check_links.check(copy)))

    def test_a_missing_local_font_is_red(self):
        copy = self.tmp / "f"
        shutil.copytree(self.out, copy)
        (copy / "assets/fonts/plus-jakarta-sans-800.woff2").unlink()
        bad = check_links.check(copy)
        self.assertTrue(any("plus-jakarta-sans-800.woff2 does not resolve" in b for b in bad), bad)

    def test_a_srcset_from_another_host_is_red(self):
        bad = self.planted("g", lambda h: h.replace("</main>", '<img src="../assets/logo.svg" srcset="../assets/logo.svg 1x, '
                                                  'https://cdn.example.com/logo@2x.png 2x" alt=""></main>'))
        self.assertTrue(any("<srcset> loads https://cdn.example.com/logo@2x.png" in b for b in bad), bad)

    def test_a_broken_local_srcset_is_red(self):
        bad = self.planted("h", lambda h: h.replace("</main>", '<img src="../assets/logo.svg" srcset="../assets/gone@2x.png 2x" alt=""></main>'))
        self.assertTrue(any("broken link ../assets/gone@2x.png" in b for b in bad), bad)

    def test_an_inline_style_from_another_host_is_red(self):
        bad = self.planted("i", lambda h: h.replace("<main", '<main style="background: url(\'https://cdn.example.com/bg.jpg\')"', 1))
        self.assertTrue(any("<style> loads https://cdn.example.com/bg.jpg" in b for b in bad), bad)

    def test_a_style_block_from_another_host_is_red(self):
        bad = self.planted("k", lambda h: h.replace("</head>", "<style>main { background: URL(//cdn.example.com/bg.jpg) }</style></head>"))
        self.assertTrue(any("<style> loads //cdn.example.com/bg.jpg" in b for b in bad), bad)

    def test_an_import_without_a_space_is_red_and_a_comment_is_not(self):
        copy = self.tmp / "l"
        shutil.copytree(self.out, copy)
        css = copy / "assets/site.css"
        css.write_text('/* the @import rule and url(nothing) are not used */\n@import"https://cdn.example.com/a.css";\n'
                       + css.read_text("utf-8"), "utf-8")
        bad = check_links.check(copy)
        self.assertTrue(any("fetches https://cdn.example.com/a.css" in b for b in bad), bad)
        self.assertFalse(any("rule" in b or "nothing" in b for b in bad), bad)

    def test_an_svg_href_to_another_host_is_red(self):
        copy = self.tmp / "j"
        shutil.copytree(self.out, copy)
        svg = copy / "assets/logo.svg"
        svg.write_text(svg.read_text("utf-8").replace("</svg>", '<image href="https://cdn.example.com/x.png"/></svg>'), "utf-8")
        bad = check_links.check(copy)
        self.assertTrue(any("logo.svg: fetches https://cdn.example.com/x.png" in b for b in bad), bad)

    def test_assets_src_arrive_byte_for_byte(self):
        src = pathlib.Path(build.SITE) / "assets-src"
        files = [f for f in src.rglob("*") if f.is_file()]
        self.assertTrue(any(f.suffix == ".woff2" for f in files) and any(f.suffix == ".svg" for f in files))
        for f in files:
            self.assertEqual((self.out / "assets" / f.relative_to(src)).read_bytes(), f.read_bytes(), f.name)

    def test_the_home_page_has_its_hero(self):
        text = (self.out / "index.html").read_text("utf-8")
        self.assertIn('<section class="hero">', text)
        self.assertEqual(text.count("<h1"), 1)
        self.assertIn('class="site-btn" href="needs/index.html"', text)        # the first door: a customer's list of needs

    def test_a_missing_optional_include_fails_a_deploy_build(self):
        import os
        ctx = build.Ctx({}, self.tmp, [], set())
        ctx.src, ctx.out = "site/pages/index.md", "index.html"
        os.environ["SITE_REQUIRE_OPTIONAL"] = "true"
        try:
            build.render("{{include? guide/01_welcome.md#No such heading}}", ctx, {}, None)
        finally:
            del os.environ["SITE_REQUIRE_OPTIONAL"]
        self.assertEqual(len(ctx.errors), 1)

    def test_a_link_to_a_samples_folder_opens_its_page(self):
        self.assertIn('href="../samples/s5_config_pack/index.html"', (self.out / "guide/04_configure_first.html").read_text("utf-8"))

    def test_a_link_to_a_missing_kit_path_fails_the_build(self):
        page = build.Page.__new__(build.Page)
        ctx = build.Ctx({}, self.tmp, [], set())
        ctx.src, ctx.out = "guide/01_welcome.md", "guide/01_welcome.html"
        ctx.url("../recipes/not_a_recipe.md")
        self.assertEqual(len(ctx.errors), 1)

    def test_an_include_of_a_missing_heading_fails_the_build(self):
        ctx = build.Ctx({}, self.tmp, [], set())
        ctx.src, ctx.out = "site/pages/index.md", "index.html"
        build.render("{{include guide/01_welcome.md#No such heading}}", ctx, {}, None)
        self.assertEqual(len(ctx.errors), 1)

    def test_no_site_page_has_an_unrendered_marker(self):
        for f in self.out.rglob("*.html"):
            text = f.read_text("utf-8")
            self.assertFalse("@@INCLUDE" in text or "{{include" in text or "{{needs:" in text or "{{api:" in text
                             or "{{samples:" in text or "{{reference-app:" in text, f.name)

    # ── the security, hosting and API pages (row LIB8) ────────────────────────────────────────────────────────────────
    def test_the_api_page_has_one_section_per_path_of_the_api_file(self):
        import yaml
        spec = yaml.safe_load((build.ROOT / build.API_SPEC).read_text("utf-8"))
        page = (self.out / "api.html").read_text("utf-8")
        heads = [html_unescape(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", page)]
        self.assertEqual([h for h in heads if h.startswith("/")], list(spec["paths"]))
        ops = sum(1 for p in spec["paths"].values() for m in build.API_METHODS if m in p)
        self.assertEqual(page.count("<strong>Sign-in:</strong>"), ops)
        self.assertEqual(page.count("<strong>Sign-in:</strong> the <code>Authorization</code> header"), ops)

    def test_an_api_file_with_a_gap_fails_the_build(self):  # canary: no summary, a $ref to nothing, a path with no method
        import yaml
        spec = yaml.safe_load((build.ROOT / build.API_SPEC).read_text("utf-8"))
        del spec["paths"]["/api/resource/Item"]["get"]["summary"]
        spec["paths"]["/api/resource/Customer"]["get"]["parameters"][0] = {"$ref": "#/components/parameters/nope"}
        spec["paths"]["/api/resource/Nothing"] = {}
        (self.tmp / "openapi_bad.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), "utf-8")
        ctx = build.Ctx({}, self.tmp, [], set())
        ctx.src, ctx.out = "site/pages/api.md", "api.html"
        with mock.patch.object(build, "ROOT", self.tmp):
            build.api_reference(ctx, "openapi_bad.yaml")
        self.assertEqual(sorted(e.split(": ", 1)[1] for e in ctx.errors),
                         ["#/components/parameters/nope names nothing", "/api/resource/Nothing has no method",
                          "GET /api/resource/Item has no summary"])

    def test_the_security_page_shows_the_templates_own_check(self):  # canary: change one character of either → RED
        page = (build.ROOT / "site/pages/security.md").read_text("utf-8")
        code = re.search(r"```python\n(.*?)```", page, re.S).group(1)
        app = (build.ROOT / "tools/app_template/service/app.py").read_text("utf-8")
        self.assertIn("def verified(", code)
        self.assertIn(code, app)
        self.assertNotIn(code.replace("300", "301").replace("SKEW_S", "SKEW"), app)

    # ── the needs catalogue (row AQCARDS) ─────────────────────────────────────────────────────────────────────────────
    def test_every_card_is_reachable_from_the_home_page_in_three_clicks(self):
        cards = [f"needs/{c.area}/{c.id}.html" for c in build.catalogue.load(build.ROOT)]
        self.assertGreater(len(cards), 0)
        self.assertEqual(unreachable(self.out, cards), [])

    def test_a_planted_orphan_card_is_unreachable_and_red(self):
        copy = self.tmp / "orphan"
        shutil.copytree(self.out, copy)
        (copy / "needs" / "till" / "planted-orphan.html").write_text("<p>no page links here</p>", "utf-8")
        self.assertEqual(unreachable(copy, ["needs/till/planted-orphan.html", "needs/till/line-quantity-cap.html"]),
                         ["needs/till/planted-orphan.html"])

    def test_a_card_four_clicks_deep_is_red(self):
        copy = self.tmp / "deep"
        shutil.copytree(self.out, copy)
        chain = ["needs/till/deep-a.html", "needs/till/deep-b.html", "needs/till/deep-c.html"]
        for here, there in zip(chain, chain[1:] + [None]):
            (copy / here).write_text(f'<a href="{posixpath.basename(there)}">x</a>' if there else "<p>end</p>", "utf-8")
        page = copy / "needs/index.html"            # one click from home; deep-a at 2, deep-b at 3, deep-c at 4
        page.write_text(page.read_text("utf-8").replace("</main>", '<a href="till/deep-a.html">x</a></main>'), "utf-8")
        self.assertEqual(unreachable(copy, chain), ["needs/till/deep-c.html"])

    def test_catalogue_json_lists_every_card(self):
        import json
        data = json.loads((self.out / "catalogue.json").read_text("utf-8"))
        self.assertEqual(sorted(d["id"] for d in data), sorted(c.id for c in build.catalogue.load(build.ROOT)))
        self.assertTrue(all((self.out / d["page"]).exists() for d in data))

    # ── what next, related needs, Plan a project (SITENEXT) ─────────────────────────────────────────────────────────
    def test_every_card_has_a_what_next_panel_by_its_verdict(self):
        ready = (self.out / "needs/till/line-quantity-cap.html").read_text("utf-8")
        part = ready[ready.index('id="what-next"'):]
        for words in ("Tell the customer", "Follow the recipe", 'href="../../recipes/till_guard.html"', "Copy the sample",
                      'href="../../samples/s23_till_guard/index.html"', 'href="../../sandbox.html"', "Run the checks", "Release"):
            self.assertIn(words, part)
        self.assertIn('href="../../plan.html?needs=line-quantity-cap"', part)
        self.assertIn("Instead:", (self.out / "needs/prices/fee-or-surcharge.html").read_text("utf-8").split('id="what-next"')[1])
        settings = (self.out / "needs/stock/branch-sees-own-stock.html").read_text("utf-8").split('id="what-next"')[1]
        self.assertNotIn("the kit's checks", settings)                      # nothing to code: checked and released as settings
        self.assertIn("Make the same settings on the customer's site", settings)
        self.assertNotIn("To lift a limit", settings)                       # its extension point shipped: no request left
        lift = (self.out / "needs/documents/invoice-layout-per-customer.html").read_text("utf-8").split('id="what-next"')[1]
        self.assertIn("To lift a limit, ask for", lift)                     # a Ready card with a request handle
        self.assertIn("P-PRINTBYPARTY", lift)
        self.assertNotIn("Until then", (self.out / "needs/till/money-columns-on-till.html").read_text("utf-8"))   # a restriction is no stop-gap
        self.assertIn("Start from:</strong> <a", (self.out / "needs/documents/receipt-own-lines.html").read_text("utf-8"))
        self.assertNotIn(">contracts/pages/receipt.md<", (self.out / "needs/documents/receipt-own-lines.html").read_text("utf-8"))
        named = (self.out / "needs/setup/country-tax-rules.html").read_text("utf-8")
        self.assertIn('(the card <a href="../integrations/outside-fiscal-result.html">', named)    # the card a limit names, linked

    def test_a_not_yet_card_waiting_on_an_extension_point_asks_for_it(self):
        # since POS train T12 no card in the kit waits on an extension point: the test plants one in a copy of the kit
        kit = self.plant_not_yet(self.planted_kit("not_yet"))
        self.assertEqual(self.build_in(kit), 0)
        ask = (self.tmp / "not_yet_out" / "needs/till/a-planted-need.html").read_text("utf-8")
        self.assertIn(build.POINT_FORM + "&amp;title=Extension-point%20request%3A%20P-PLANTED", ask)
        self.assertIn(f"({build.MEMBERS_ONLY}; ", html_unescape(ask))         # the request form is members-only: it says so
        self.assertIn("Until then, today:</strong> the check before payment", ask)
        self.assertNotIn("Copy the sample", ask[ask.index('id="what-next"'):])

    def test_every_private_link_says_so_where_it_is_rendered(self):
        # the request steps (build.py; the ask step: the Not yet test above), the reference apps (gallery.py) and Plan a
        # project's requests (catalogue.json; plan.js: test_plan.mjs)
        note = build.MEMBERS_ONLY
        lift = html_unescape((self.out / "needs/documents/invoice-layout-per-customer.html").read_text("utf-8"))
        self.assertIn(f"(the extension-point request; {note}).", lift.split('id="what-next"')[1])
        apps = html_unescape((self.out / "reference_apps.html").read_text("utf-8"))
        cards = re.findall(r'<li class="card"><h3>.*?</li>', apps)
        self.assertGreaterEqual(len(cards), 2)
        self.assertTrue(all(f'<p class="note">N{build.NOT_OPEN_YET[1:]}.</p>' in c for c in cards), cards)
        forms = [f for d in json.loads((self.out / "catalogue.json").read_text("utf-8")) for f in d["request_forms"]]
        self.assertTrue(forms and all(f["note"] == note for f in forms))
        self.assertTrue(all(check_links.PRIVATE_CLAUSE in n for n in (note, build.NOT_OPEN_YET)))

    def test_a_private_link_on_a_page_that_does_not_say_so_is_red_and_an_unlisted_repository_too(self):
        repo = "https://github.com/ivendnext-developers/"
        bad = self.planted("members", lambda h: h.replace("</main>", f'<a href="{repo}3pl-shipping">x</a></main>'))
        self.assertTrue(any("01_welcome.html: links the private repository 3pl-shipping" in b for b in bad), bad)
        said = self.planted("members_said", lambda h: h.replace("</main>", f'<a href="{repo}3pl-shipping">x</a> (GitHub shows '
                                                                            f'&quot;page not\n found&quot; to others)</main>'))
        self.assertEqual(said, [])
        self.assertEqual(self.planted("public_repo", lambda h: h.replace("</main>", f'<a href="{repo}.github">x</a></main>')), [])
        bad = self.planted("unlisted", lambda h: h.replace("</main>", f'<a href="{repo.upper()}New-Repo.git">x</a></main>'))
        self.assertTrue(any("links ivendnext-developers/new-repo, which is on neither list" in b for b in bad), bad)

    def test_the_request_form_is_the_feedback_pages_own_address(self):
        # the form lives in a private repository the link check does not follow: hold it to the feedback page's address
        self.assertIn(f"]({build.POINT_FORM})", (build.SITE / "pages/feedback.md").read_text("utf-8"))

    def test_a_panel_with_a_broken_link_is_red(self):
        out = self.tmp / "broken-panel"
        with mock.patch.dict(build.DOOR_NEXT, {"till-key": "See [the page](site:no-such-page.html)."}):
            self.assertEqual(build.build(out), 0)
        bad = check_links.check(out)
        self.assertTrue(any("warranty-check-at-till.html: broken link" in b for b in bad), bad[:3])

    def test_every_door_is_in_one_build_step_and_a_missing_one_is_red(self):
        self.assertEqual(build.order_errors(), [])
        with mock.patch.object(build, "BUILD_ORDER", build.BUILD_ORDER[1:]):
            self.assertTrue(any("door configure is in no step" in e for e in build.order_errors()))

    def test_related_needs_named_first_then_sample_then_chapter_15_at_most_four(self):
        cards = build.catalogue.load(build.ROOT)
        rel = build.related_needs(cards, build.named_together())
        self.assertTrue(all(len(v) <= 4 and all(o.id != k for o in v) for k, v in rel.items()))
        self.assertEqual(rel["question-on-quantity-change"][0].id, "line-quantity-cap")      # named in its limit
        self.assertIn("prescription-before-payment", [o.id for o in rel["prescriptions-as-records"]])   # a chapter 15 row
        text = (self.out / "needs/till/question-on-quantity-change.html").read_text("utf-8")
        self.assertIn('id="related-needs"', text)

    def test_catalogue_json_carries_what_the_shortlist_needs(self):
        import json
        data = {d["id"]: d for d in json.loads((self.out / "catalogue.json").read_text("utf-8"))}
        d = data["line-quantity-cap"]
        self.assertEqual(d["build_step"], build.build_step("check-before-payment"))
        self.assertEqual(d["recipes"][0]["page"], "recipes/till_guard.html")
        self.assertEqual(d["samples"][0]["page"], "samples/s23_till_guard/index.html")
        rows, _ = build.catalogue.blueprint_rows(build.catalogue.load(build.ROOT), ["line-quantity-cap"])
        self.assertEqual("| 1 " + d["blueprint_row"], rows[0])
        proofs = [p for x in data.values() for p in x["recipes"] + x["samples"]]
        self.assertTrue(all(bool(p["page"]) != bool(p["url"]) for p in proofs))           # a site page, or the file on GitHub
        self.assertTrue(all((self.out / p["page"]).exists() for p in proofs if p["page"]))
        self.assertTrue(all(p["url"].startswith(build.REPO_URL + "/") for p in proofs if p["url"]))
        guide = [p for p in data["list-columns"]["recipes"] if p["path"] == "guide/04_configure_first.md"][0]
        self.assertEqual(guide["page"], "guide/04_configure_first.html")

    def test_plan_page_without_script_keeps_its_seven_steps_and_hides_the_tool(self):
        text = (self.out / "plan.html").read_text("utf-8")
        self.assertIn('<section id="plan-tool" class="plan-tool"', text)
        self.assertRegex(text, r'<section id="plan-tool"[^>]* hidden>')
        steps = text[text.index('id="the-steps"'):text.index('id="what-is-refused"')]
        self.assertEqual(steps.count("<li>"), 7)
        self.assertIn('href="kit/blueprint.html"', steps)
        self.assertIn('<script src="assets/plan.js" defer></script>', text)
        self.assertTrue((self.out / "assets/plan.js").exists())

    def test_chapter_16_carries_the_tables_built_from_the_cards(self):
        text = (self.out / "guide/16_possible_not_possible.html").read_text("utf-8")
        self.assertIn('href="../needs/till/line-quantity-cap.html"', text)          # Possible today
        self.assertIn('href="../needs/prices/fee-or-surcharge.html"', text)          # When the product has no door

    def test_recipes_and_samples_show_the_needs_they_serve_and_a_reference_recipe_shows_none(self):
        self.assertIn('id="needs-this-serves"', (self.out / "recipes/till_guard.html").read_text("utf-8"))
        self.assertIn('id="needs-this-serves"', (self.out / "samples/s23_till_guard/index.html").read_text("utf-8"))
        self.assertNotIn('id="needs-this-serves"', (self.out / "recipes/sign_in.html").read_text("utf-8"))

    def planted_kit(self, name: str, also: tuple = ()) -> pathlib.Path:
        """A copy of the kit (its folders linked, needs/, recipes/ and samples/ copied, and the folders in `also`) a test may
        plant a fault in. In samples/ only the READMEs are copied; every other file is linked, so a copy costs no megabytes."""
        kit = self.tmp / name
        kit.mkdir()
        for entry in build.ROOT.iterdir():
            if entry.name in ("needs", "recipes", "samples", ".git") + also:
                continue
            (kit / entry.name).symlink_to(entry)
        for folder in also:
            shutil.copytree(build.ROOT / folder, kit / folder)
        shutil.copytree(build.ROOT / "needs", kit / "needs")
        shutil.copytree(build.ROOT / "recipes", kit / "recipes")
        shutil.copytree(build.ROOT / "samples", kit / "samples", ignore=shutil.ignore_patterns("__pycache__"),
                        copy_function=lambda src, dst: (shutil.copy2 if src.endswith("README.md") else
                                                       lambda s, d: pathlib.Path(d).symlink_to(s))(src, dst))
        return kit

    PLANTED_NOT_YET = """---
id: a-planted-need
title: A planted need that waits on an extension point
area: till
topic: questions-during-the-sale
asks: A planted need that waits on an extension point
status: not-yet
door: request
blocked-by: extension-point
recipe: none
sample: none
request: P-PLANTED
verified: planted by the site's tests
---
## What you build
Nothing yet: it waits on the extension point P-PLANTED.

## Limits
- Today the check before payment can refuse the sale at Pay (the card *line-quantity-cap*).

## Tell the customer
The till cannot do this yet; it can stop the sale at Pay.
"""

    def plant_not_yet(self, kit: pathlib.Path) -> pathlib.Path:
        """Plant a Not yet card waiting on an extension point (`needs/till/a-planted-need.md`) in a planted kit."""
        (kit / "needs" / "till" / "a-planted-need.md").write_text(self.PLANTED_NOT_YET, "utf-8")
        return kit

    def build_in(self, kit: pathlib.Path) -> int:
        real = build.ROOT
        build.ROOT = kit
        try:
            return build.build(self.tmp / (kit.name + "_out"))
        finally:
            build.ROOT = real

    def test_a_card_with_an_unknown_door_fails_the_site_build(self):
        kit = self.planted_kit("door")
        self.assertEqual(self.build_in(kit), 0)
        card = kit / "needs" / "till" / "line-quantity-cap.md"
        card.write_text(card.read_text("utf-8").replace("door: check-before-payment", "door: back-door"), "utf-8")
        self.assertEqual(self.build_in(kit), 1)

    def test_a_recipe_no_card_cites_and_not_listed_as_reference_fails_the_site_build(self):
        kit = self.planted_kit("orphan_recipe")
        (kit / "recipes" / "zz_orphan.md").write_text("# An orphan recipe\n\nNo card cites it. It exists only in this test of the site build, and this paragraph is long enough to be its description.\n", "utf-8")
        self.assertEqual(self.build_in(kit), 1)
        with (kit / "needs" / "reference.txt").open("a", encoding="utf-8") as f:
            f.write("recipes/zz_orphan.md — a planted reference recipe\n")
        self.assertEqual(self.build_in(kit), 0)

    # ── reference apps and samples: one card each, built from the READMEs (row SITECARDS) ──────────────────────────────
    def edit_readme(self, kit: pathlib.Path, sample: str, edit) -> None:
        f = kit / "samples" / sample / "README.md"
        f.write_text(edit(f.read_text("utf-8")), "utf-8")

    def test_every_sample_and_every_reference_app_has_one_card_on_the_page(self):
        page = (self.out / "reference_apps.html").read_text("utf-8")
        folders = sorted(p.parent.name for p in (build.ROOT / "samples").glob("*/README.md"))
        linked = re.findall(r'<li class="card">(?:<a class="thumb"[^>]*>.*?</a>)?<h4><a href="samples/([^/"]+)/index.html"', page)
        self.assertEqual(sorted(linked), folders)
        spec = (build.ROOT / "site" / "pages" / "reference_apps.md").read_text("utf-8")
        apps = len(re.findall(r"^\{\{reference-app: ", spec, re.M))
        self.assertGreaterEqual(apps, 2)
        self.assertEqual(len(re.findall(r'<li class="card"><h3>', page)), apps)
        flat = (self.out / "samples" / "index.html").read_text("utf-8")
        self.assertEqual(sorted(re.findall(r'<h2><a href="([^/"]+)/index.html"', flat)), folders)

    def test_a_card_shows_its_door_its_run_step_and_its_links(self):
        page = (self.out / "reference_apps.html").read_text("utf-8")
        card = page.split('<h4><a href="samples/s23_till_guard/index.html"', 1)[1].split("</li>")[0]   # a card with a picture has a thumbnail link first
        self.assertIn("Check before payment", card)
        self.assertIn("python3 -m unittest discover -s samples/s23_till_guard/tests", card)
        self.assertIn("index.html#run-it", card)
        self.assertIn(f"{build.REPO_URL}/tree/main/samples/s23_till_guard", card)

    def test_a_card_whose_github_folder_names_no_samples_folder_is_red(self):
        def bad_folders(text: str) -> list[str]:         # check_links.py does not follow other hosts, so the kit tree is read here
            return [f for f in re.findall(re.escape(build.REPO_URL) + r'/tree/main/(samples/[^"#]+)', text) if not (build.ROOT / f).is_dir()]
        page = (self.out / "reference_apps.html").read_text("utf-8")
        self.assertEqual(bad_folders(page), [])
        self.assertEqual(len(re.findall(re.escape(build.REPO_URL) + r'/tree/main/samples/', page)), len(list((build.ROOT / "samples").glob("*/README.md"))))
        self.assertEqual(bad_folders((self.out / "samples" / "index.html").read_text("utf-8")), [])
        self.assertEqual(bad_folders(page.replace("tree/main/samples/s23_till_guard", "tree/main/samples/s99_nothing")), ["samples/s99_nothing"])

    def test_a_card_screenshot_that_does_not_resolve_is_red(self):
        copy = self.tmp / "shot"
        shutil.copytree(self.out, copy)
        still = "screenshots/01_till_sale_with_offers.png"                               # the first still: a GIF only when there is none
        self.assertIn(f'src="samples/s3_price_audit/{still}"', (copy / "reference_apps.html").read_text("utf-8"))          # the card shows it ...
        self.assertIn(f'src="s3_price_audit/{still}"', (copy / "samples/index.html").read_text("utf-8"))
        (copy / "samples/s3_price_audit" / still).unlink()
        bad = check_links.check(copy)                                                    # ... and a missing file is red on each page
        self.assertTrue(any(b.startswith("reference_apps.html") and "01_till_sale" in b for b in bad), bad)
        self.assertTrue(any(b.startswith("samples/index.html") and "01_till_sale" in b for b in bad), bad)
        self.assertNotIn(".gif", re.sub(r"<a href=[^>]*>", "", "".join(re.findall(r'<img src="[^"]*"', (copy / "reference_apps.html").read_text("utf-8")))))

    def test_a_sample_with_no_run_section_fails_the_site_build(self):
        kit = self.planted_kit("norun")
        self.assertEqual(self.build_in(kit), 0)
        self.edit_readme(kit, "s23_till_guard", lambda t: t.replace("## Run it", "## Running"))
        self.assertEqual(self.build_in(kit), 1)

    def test_the_how_to_run_it_heading_also_counts(self):
        kit = self.planted_kit("howto")
        self.edit_readme(kit, "s23_till_guard", lambda t: t.replace("## Run it", "## How to run it"))
        self.assertEqual(self.build_in(kit), 0)

    def test_a_sample_with_no_door_fails_the_site_build(self):
        kit = self.planted_kit("nodoor")
        self.edit_readme(kit, "s3_price_audit", lambda t: re.sub(r"^\*\*Door:\*\*.*\n\n", "", t, flags=re.M))
        self.assertEqual(self.build_in(kit), 1)

    def test_a_door_of_none_or_request_or_off_the_list_fails_the_site_build(self):
        kit = self.planted_kit("baddoor")
        self.assertEqual(self.build_in(kit), 0)
        for door in ("None", "Request", "Back door", "outside-app"):
            self.edit_readme(kit, "s3_price_audit", lambda t, d=door: re.sub(r"^\*\*Door:\*\*.*$", f"**Door:** {d}", t, flags=re.M))
            self.assertEqual(self.build_in(kit), 1, door)

    def test_a_door_line_on_a_sample_a_card_cites_fails_the_site_build(self):
        kit = self.planted_kit("doublydoor")
        self.edit_readme(kit, "s23_till_guard", lambda t: t.replace("## Run it", "**Door:** Check before payment\n\n## Run it", 1))
        self.assertEqual(self.build_in(kit), 1)

    def test_the_page_groups_the_cards_by_door_under_a_list_of_anchors(self):
        page = (self.out / "reference_apps.html").read_text("utf-8")
        self.assertIn('<nav aria-label="Samples by door">', page)
        self.assertIn('<a href="#check-before-payment">Check before payment</a>', page)
        group = page.split('<h3 id="check-before-payment">', 1)[1].split("<h3 ", 1)[0]
        self.assertIn('href="samples/s23_till_guard/index.html"', group)

    def test_a_sample_only_not_yet_cards_cite_needs_its_own_door_line(self):
        kit = self.planted_kit("requestdoor")
        folder = kit / "samples" / "s99_planted"
        folder.mkdir()
        (folder / "README.md").write_text("# S99 — a planted sample\n\nIt only exists in this test of the site build, and this first paragraph is long enough to be its description.\n\n**When to use it:** never.\n\n"
                                          "## Run it\n\n```bash\npython3 -m unittest\n```\n", "utf-8")
        card = self.plant_not_yet(kit) / "needs" / "till" / "a-planted-need.md"         # a not-yet card: its door is Request
        card.write_text(card.read_text("utf-8").replace("sample: none", "sample: samples/s99_planted"), "utf-8")
        self.assertEqual(self.build_in(kit), 1)                                          # no door from the card, none in the README
        self.edit_readme(kit, "s99_planted", lambda t: t.replace("## Run it", "**Door:** Manifest\n\n## Run it", 1))
        self.assertEqual(self.build_in(kit), 0)                                          # its own line is allowed

    def test_a_run_step_shows_at_most_four_lines(self):
        import gallery
        lines, head = gallery.run_step("# S\n\n## Run it\n\n```bash\n" + "\n".join(f"cmd {n}" for n in range(9)) + "\n```\n\n## Next\n")
        self.assertEqual((lines, head), ([f"cmd {n}" for n in range(4)], "Run it"))
        self.assertEqual(gallery.run_step("# S\n\n## Running\n\n```bash\ncmd\n```\n"), ([], ""))
        self.assertEqual(gallery.run_step("# S\n\n## Run it\n\nJust words, no code.\n"), ([], "Run it"))

    def test_a_planted_extra_sample_gets_a_card_with_no_code_change(self):
        kit = self.planted_kit("extra")
        folder = kit / "samples" / "s99_planted"
        folder.mkdir()
        (folder / "README.md").write_text("# S99 — a planted sample\n\nIt only exists in this test of the site build, and this first paragraph is long enough to be its description.\n\n**When to use it:** never.\n\n"
                                          "**Door:** Manifest\n\n## Run it\n\n```bash\npython3 -m unittest\n```\n", "utf-8")
        with (kit / "needs" / "reference.txt").open("a", encoding="utf-8") as f:
            f.write("samples/s99_planted — a planted sample\n")
        self.assertEqual(self.build_in(kit), 0)
        page = (self.tmp / "extra_out" / "reference_apps.html").read_text("utf-8")
        self.assertIn('href="samples/s99_planted/index.html"', page)
        self.assertIn('href="s99_planted/index.html"', (self.tmp / "extra_out" / "samples" / "index.html").read_text("utf-8"))

    def test_a_first_screenshot_that_is_not_in_the_folder_fails_the_site_build(self):
        kit = self.planted_kit("noshot")
        self.edit_readme(kit, "s23_till_guard", lambda t: re.sub(r"^(# .+)$", r"\1\n\n![x](screenshots/not_there.png)", t, count=1, flags=re.M))
        self.assertEqual(self.build_in(kit), 1)

    def test_a_reference_app_card_with_a_status_off_the_list_fails_the_site_build(self):
        for bad in ("A | one | Outside app | Almost done | repo", "A | one | Outside app | Brief ready | ", "A | one | Back door | Brief ready | repo",
                    "A | one | Outside app, None | Brief ready | repo"):
            ctx = build.Ctx({}, self.tmp, [], set())
            ctx.src, ctx.out = "site/pages/reference_apps.md", "reference_apps.html"
            build.render("{{reference-app: " + bad + "}}", ctx, {}, None)
            self.assertEqual(len(ctx.errors), 1, bad)
        ctx = build.Ctx({}, self.tmp, [], set())
        build.render("{{reference-app: A | one | Outside app, Till key | Brief ready | repo-1}}", ctx, {}, None)
        self.assertEqual(ctx.errors, [])

    # ── partner calls by their iVendNext names (ivendnext_mpos.api.v1) ─────────────────────────────────────────────
    def test_no_site_page_names_an_upstream_call(self):
        for f in self.out.rglob("*.html"):
            self.assertEqual(upstream_calls(f.read_text("utf-8")), [], f.relative_to(self.out))

    def test_an_upstream_call_on_a_page_is_red(self):
        self.assertEqual(upstream_calls("POST /api/method/erpnext.stock.utils.scan_barcode"),
                         ["erpnext.stock.utils.scan_barcode"])

    # ── the forms and the sandbox request (row SITEFORMS) ─────────────────────────────────────────────────────────
    def test_the_sandbox_page_links_the_partner_form_and_no_page_links_the_retired_form(self):
        self.assertIn(f'href="{PARTNER_FORM}"', (self.out / "sandbox.html").read_text("utf-8"))
        for f in self.out.rglob("*.html"):
            self.assertNotIn("sandbox_request", f.read_text("utf-8"), f.name)
        self.assertFalse((build.ROOT / ".github" / "ISSUE_TEMPLATE" / "sandbox_request.yml").exists())

    def test_the_feedback_page_links_the_four_forms_in_the_private_repository_and_none_in_the_kit(self):
        text = (self.out / "feedback.html").read_text("utf-8")
        for n, form in enumerate(issue_forms.FORMS, 1):
            self.assertIn(f"/ivendnext-developers/partner-feedback/issues/new?template={n}_{form}.yml", text)
        self.assertNotIn("/partner-kit/issues/new", text)
        self.assertIn("Every member can read every issue", text)
        self.assertIn(PARTNER_FORM, text)

    def test_the_four_forms_are_within_the_cap_and_have_no_sent_by(self):
        for form in issue_forms.FORMS:
            md = (build.ROOT / "feedback" / f"{form}.md").read_text("utf-8")
            self.assertEqual(issue_forms.cap_problems(form, md), [], form)
            self.assertNotIn("Sent by", md)
            self.assertNotIn("Sent by", issue_forms.form_yaml(form))

    def test_a_form_with_a_sixth_field_is_red(self):
        md = (build.ROOT / "feedback" / "kit_defect.md").read_text("utf-8")
        md = md.replace("- [ ] It touches", "## 4. One more (optional)\n<x>\n\n## 5. And another (optional)\n<y>\n\n- [ ] It touches", 1)
        bad = issue_forms.cap_problems("kit_defect", md)
        self.assertTrue(any("6 fields" in b for b in bad), bad)

    def test_a_form_with_a_fourth_required_field_is_red(self):
        md = (build.ROOT / "feedback" / "recipe_or_document_gap.md").read_text("utf-8")
        md = md.replace(" (optional)", "", 1).replace("\n```\n\n## What we may ask", "\n\n## 4. One more\n<x>\n```\n\n## What we may ask", 1)
        bad = issue_forms.cap_problems("recipe_or_document_gap", md)
        self.assertTrue(any("4 required fields" in b for b in bad), bad)
        self.assertEqual(issue_forms.cap_problems("recipe_or_document_gap", md.replace("## 4. One more", "## 4. One more (optional)")), [])

    def check_forms_in(self, name: str, edit) -> int:
        """Run the generator's own --check over a copy of .github/ISSUE_TEMPLATE that `edit` has changed."""
        copy = self.tmp / name
        shutil.copytree(build.ROOT / ".github" / "ISSUE_TEMPLATE", copy)
        edit(copy)
        real, argv = issue_forms.OUT, sys.argv
        issue_forms.OUT, sys.argv = copy, ["issue_forms.py", "--check"]
        try:
            return issue_forms.main()
        finally:
            issue_forms.OUT, sys.argv = real, argv

    def test_the_forms_check_is_green_on_the_real_forms_and_red_on_each_kind_of_drift(self):
        self.assertEqual(self.check_forms_in("f0", lambda d: None), 0)
        for n, form in enumerate(issue_forms.FORMS, 1):    # every one of the four generated forms, not only the first
            f = f"{n}_{form}.yml"
            self.assertEqual(self.check_forms_in(f"f{n}", lambda d, f=f: (d / f).write_text((d / f).read_text("utf-8") + "# x\n", "utf-8")), 1, f)
        self.assertEqual(self.check_forms_in("fc", lambda d: (d / "config.yml").write_text("blank_issues_enabled: true\n", "utf-8")), 1)
        self.assertEqual(self.check_forms_in("fx", lambda d: (d / "sandbox_request.yml").write_text("name: x\n", "utf-8")), 1)
        self.assertEqual(self.check_forms_in("fm", lambda d: (d / "1_kit_defect.yml").unlink()), 1)

    def test_a_form_with_two_tick_boxes_or_a_repeated_id_is_red(self):
        md = (build.ROOT / "feedback" / "kit_defect.md").read_text("utf-8")
        self.assertEqual(issue_forms.cap_problems("kit_defect", md), [])
        two = md.replace("- [ ] It touches a sale, a price or a payment", "- [ ] It touches a sale, a price or a payment\n- [ ] And another", 1)
        ids = [f["id"] for f in issue_forms.parse(two)[3]]
        self.assertEqual(len(ids), len(set(ids)), ids)           # each tick box gets its own id
        twice = md.replace("## 2. What you expected", "## 1. What you expected", 1)
        self.assertTrue(any("share an id" in b for b in issue_forms.cap_problems("kit_defect", twice)))

    def test_the_kit_defect_form_asks_for_the_piece_and_its_version(self):
        text = (build.ROOT / ".github" / "ISSUE_TEMPLATE" / "1_kit_defect.yml").read_text("utf-8")
        self.assertIn('label: "Kit piece and version"', text)

    # ── findable: titles, descriptions, structured data, preview images, dates, llms.txt, redirects (row SITESEO) ─────────
    def html_of(self, out: str) -> str:
        return (self.out / out).read_text("utf-8")

    def meta(self, text: str, attr: str, key: str) -> str:
        m = re.search(rf'<meta {attr}="{re.escape(key)}" content="([^"]*)"', text)
        return html_unescape(m.group(1)) if m else ""

    def test_titles_follow_the_rule_and_none_is_duplicated_or_starts_with_a_digit(self):
        titles = {}
        for out, text in page_texts(self.out).items():
            t = html_unescape(re.search(r"<title>(.*?)</title>", text).group(1))
            titles[out] = t
            self.assertEqual(self.meta(text, "property", "og:title"), t, out)
            self.assertEqual(self.meta(text, "property", "og:site_name"), "iVendNext Developers", out)
            if out != "index.html" and t.endswith(" · iVendNext Developers"):
                self.assertLessEqual(len(t), 65, out)                               # the site name only where it fits
        bad, warn = seo.title_problems(titles)
        self.assertEqual(bad, [])
        for w in warn:
            print("  warning:", w)
        self.assertEqual(titles["index.html"], "iVendNext Developers: build custom retail POS apps, integrations and extensions")
        self.assertEqual(titles["guide/04_configure_first.html"], "Configure first · iVendNext Developers")
        self.assertEqual(titles["needs/till/warranty-check-at-till.html"], "A warranty check at the till · iVendNext Developers")

    def test_a_planted_bad_title_is_red_and_a_long_one_only_warns(self):
        bad, warn = seo.title_problems({"a.html": "Same · iVendNext Developers", "b.html": "Same · iVendNext Developers"})
        self.assertTrue(any("same as a.html" in b for b in bad), bad)
        bad, _ = seo.title_problems({"c.html": "4. Configure first"})
        self.assertTrue(any("starts with a digit" in b for b in bad), bad)
        bad, warn = seo.title_problems({"d.html": "x" * 91, "e.html": "y" * 70})
        self.assertEqual([b.split(":")[0] for b in bad], ["d.html"])
        self.assertEqual([w.split(":")[0] for w in warn], ["e.html"])
        self.assertEqual(seo.title_of("4. Configure first"), "Configure first · iVendNext Developers")
        self.assertEqual(seo.title_of("13a. Screens"), "Screens · iVendNext Developers")
        self.assertEqual(seo.title_of("w" * 50), "w" * 50)                          # 50 + the site name is over 65: the name alone

    def test_every_page_has_a_description_of_120_to_160_and_the_20_by_hand_are_used(self):
        descs = {out: self.meta(text, "name", "description") for out, text in page_texts(self.out).items()}
        self.assertEqual(seo.desc_problems(descs), [])
        hand = seo.load(build.SEO_JSON)[0]["descriptions"]
        self.assertGreaterEqual(len(hand), 20)
        spec = {"index.html", "start.html", "needs/index.html", "build.html", "plan.html", "sandbox.html", "publish.html", "hosting.html",
                "reference_apps.html", "samples/index.html", "recipes/index.html", "guide/03_ladder_and_never_list.html",
                "guide/04_configure_first.html", "guide/09_points_and_requests.html", "guide/16_possible_not_possible.html",
                "recipes/connected_app.html", "recipes/configure_no_code.html", "recipes/till_guard.html", "recipes/manifest.html",
                "recipes/rule_guard.html"}                                                  # the 20 pages of the lane's decision 2 (the recipes: most cited by cards)
        self.assertEqual(spec - set(hand), set())
        for out, d in hand.items():
            self.assertEqual(descs[out], d, out)

    def test_a_planted_bad_description_is_red(self):
        ok = "x" * 130
        self.assertEqual(seo.desc_problems({"a": ok, "b": ok + "y"}), [])
        bad = seo.desc_problems({"a": "x" * 119, "b": "x" * 161, "c": "", "d": ok, "e": ok})
        for page, word in (("a", "119 characters"), ("b", "161 characters"), ("c", "no description"), ("e", "same as d")):
            self.assertTrue(any(b.startswith(page + ":") and word in b for b in bad), (page, bad))

    def test_a_description_by_rule_is_the_first_sentences_cut_at_a_sentence_end(self):
        s1, s2, s3 = "A" * 80 + ".", "B" * 50 + ".", "C" * 70 + "."
        self.assertEqual(seo.fit(f"{s1} {s2} {s3}"), f"{s1} {s2}")                      # long enough after two sentences: stop at the sentence end
        short = seo.fit("Too short.", "recipe")                                          # a page that says too little gets its kind's sentence
        self.assertIn("A recipe for builders on iVendNext.", short)
        cut = seo.fit("word " * 40)                                                      # one long sentence: cut at a word
        self.assertTrue(120 <= len(cut) <= 160 and cut.endswith("…"), cut)
        clause = seo.fit("Ready, with limits. " + "word " * 18 + "of it; " + "more " * 30)  # a long text is cut at a clause, never on "of"
        self.assertTrue(120 <= len(clause) <= 160 and not clause.rstrip("…").endswith(" of"), clause)

    # structured data
    def test_every_page_has_valid_structured_data_of_the_allowed_types(self):
        pages = page_texts(self.out)
        locs = set(re.findall(r"<loc>([^<]+)</loc>", self.html_of("sitemap.xml")))
        for out, text in pages.items():
            self.assertEqual(seo.ld_problems(text, locs), [], out)
            self.assertEqual(text.count('type="application/ld+json"'), 1, out)               # one block a page
            self.assertNotIn("FAQPage", text, out)
            self.assertNotIn("HowTo", text, out)
        home = self.html_of("index.html")
        for needle in ('"@type": "Organization"', '"@type": "WebSite"', '"@type": "SearchAction"',
                       '"urlTemplate": "https://developer.ivendnext.com/search.html?q={search_term_string}"'):
            self.assertIn(needle, home)
        self.assertNotIn('"BreadcrumbList"', home)                                      # nothing below Home to list
        for out, text in pages.items():
            if out != "index.html":
                self.assertIn('<nav class="crumbs"', text, out)                         # the line the markup states is on the page
                self.assertIn('"@type": "BreadcrumbList"', text, out)
            lists = ("guide/index.html", "recipes/index.html", "samples/index.html", "feedback/index.html")
            article = (re.match(r"(guide|recipes|kit)/[^/]+\.html$|samples/[^/]+/index\.html$|needs/[a-z]+/[^/]+\.html$", out)
                       and out not in lists and not out.endswith("/index.html") or re.fullmatch(r"samples/[^/]+/index\.html", out)) and not out.startswith(
                ("needs/status/", "needs/door/", "needs/all", "needs/not-possible"))
            self.assertEqual('"@type": "TechArticle"' in text, bool(article), out)

    def test_a_page_without_its_meta_fails_the_build_and_a_title_override_needs_a_long_heading(self):
        with self.assertRaises(ValueError):
            build.shell("X", "<p>x</p>", "x.html")                                       # it would silently drop out of search
        self.assertIn("noindex", build.shell("X", "<p>x</p>", "x.html", noindex=True))
        kit = self.planted_kit("title_override")
        table = self.tmp / "title_override_seo.json"
        data = json.loads(build.SEO_JSON.read_text("utf-8"))
        data["titles"]["start.html"] = "A title written where the heading is short enough"        # start.html's own heading is short
        table.write_text(json.dumps(data), "utf-8")
        with mock.patch.object(build, "SEO_JSON", table):
            self.assertEqual(self.build_in(kit), 1)
        data["titles"].pop("start.html")
        data["titles"]["needs/till/warranty-check-at-till.html"] = "x" * 20                    # a card's title is its own line, unchanged
        table.write_text(json.dumps(data), "utf-8")
        with mock.patch.object(build, "SEO_JSON", table):
            self.assertEqual(self.build_in(kit), 1)

    def test_a_planted_bad_block_is_red(self):
        locs = {"https://developer.ivendnext.com/", "https://developer.ivendnext.com/start.html"}
        page = lambda block, nav="": ('<nav class="crumbs"><ol><li><a href="x">Home</a></li><li aria-current="page">Start</li></ol></nav>'
                                      '<script type="application/ld+json">' + block + "</script>")
        crumb = ('{"@context": "https://schema.org", "@graph": [{"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", '
                 '"position": 1, "name": "Home", "item": "https://developer.ivendnext.com/"}, {"@type": "ListItem", "position": 2, '
                 '"name": "Start", "item": "https://developer.ivendnext.com/start.html"}]}]}')
        self.assertEqual(seo.ld_problems(page(crumb), locs), [])
        self.assertTrue(any("not JSON" in b for b in seo.ld_problems(page('{"@type": '), locs)))
        self.assertTrue(any("FAQPage" in b for b in seo.ld_problems(page('{"@context": "https://schema.org", "@type": "FAQPage"}'), locs)))
        self.assertTrue(any("not a page of the site" in b for b in seo.ld_problems(page(crumb.replace("start.html", "gone.html")), locs)))
        self.assertTrue(any("not the line the page shows" in b for b in seo.ld_problems(page(crumb.replace('"Start"', '"Begin"')), locs)))

    # preview images
    def test_every_page_has_its_kinds_preview_image_of_1200_by_630_under_150_kb(self):
        for out, text in page_texts(self.out).items():
            kind = ("home" if out == "index.html" else "card" if re.fullmatch(r"needs/[a-z]+/[^/]+\.html", out) and "index.html" not in out
                    and not out.startswith(("needs/status/", "needs/door/")) and out not in ("needs/all.html", "needs/not-possible.html")
                    else "needs" if out.startswith("needs/") else "guide" if out.startswith(("guide/", "kit/")) else "recipes"
                    if out.startswith("recipes/") else "samples" if out.startswith("samples/") else "home")
            self.assertEqual(self.meta(text, "property", "og:image"), f"https://developer.ivendnext.com/assets/og/{kind}.png", out)
            self.assertEqual(self.meta(text, "property", "og:image:width"), "1200", out)
            self.assertEqual(self.meta(text, "property", "og:image:height"), "630", out)
            self.assertEqual(self.meta(text, "name", "twitter:card"), "summary_large_image", out)
            self.assertEqual(self.meta(text, "property", "og:image:alt"), seo.OG_ALT[kind], out)
        self.assertEqual(og_problems({k: self.out / "assets" / "og" / f"{k}.png" for k in seo.OG_KINDS}), [])
        self.assertTrue((self.out / "assets" / "logo.svg").is_file())                   # the Organization's logo address is a built file

    def test_a_planted_bad_preview_image_is_red(self):
        import struct, zlib
        def png(w, h, pad=0):
            raw = b"\x00" + b"\x00\x00\x00" * w
            def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw * h)) + chunk(b"tEXt", b"x" * pad) + chunk(b"IEND", b""))
        d = self.tmp / "og_plant"
        d.mkdir()
        (d / "a.png").write_bytes(png(1200, 630))
        (d / "b.png").write_bytes(png(600, 315))
        (d / "c.png").write_bytes(png(1200, 630, pad=151_000))
        bad = og_problems({"a": d / "a.png", "b": d / "b.png", "c": d / "c.png", "d": d / "gone.png"})
        self.assertEqual([b.split(":")[0] for b in bad], ["b", "c", "d"], bad)

    # sitemap dates
    def test_sitemap_dates_are_commit_dates_never_in_the_future_and_none_for_a_page_without_one(self):
        import datetime, subprocess
        xml = self.html_of("sitemap.xml")
        self.assertEqual(lastmod_problems(xml, (datetime.date.today() + datetime.timedelta(days=1)).isoformat()), [])
        if seo.git_dates(build.ROOT) is None:
            self.skipTest("a shallow clone: no dates (the deploy build refuses one)")
        git = lambda *paths: max(subprocess.run(["git", "-C", str(build.ROOT), "log", "-1", "--format=%cs", "--", p], capture_output=True, text=True).stdout.strip() for p in paths)
        out, want = "guide/04_configure_first.html", git("guide/04_configure_first.md")            # a page of one source: exactly that date
        m = re.search(rf"<loc>https://developer.ivendnext.com/{re.escape(out)}</loc><lastmod>([^<]*)</lastmod>", xml)
        self.assertTrue(m, out)
        self.assertEqual(m.group(1), want, out)
        self.assertIn(f'"dateModified": "{want}"', self.html_of(out))
        card = "needs/till/warranty-check-at-till"                                                  # a card: its own file, its related cards and the recipe it names
        got = re.search(rf"<loc>https://developer.ivendnext.com/{card}.html</loc><lastmod>([^<]*)</lastmod>", xml).group(1)
        self.assertGreaterEqual(got, git(card + ".md"))
        own = subprocess.run(["git", "-C", str(build.ROOT), "log", "-1", "--format=%cs", "--", "site/pages/start.md"], capture_output=True, text=True).stdout.strip()
        got = re.search(r"<loc>https://developer.ivendnext.com/start.html</loc><lastmod>([^<]*)</lastmod>", xml).group(1)
        self.assertGreaterEqual(got, own)                                                # a page that pulls in sections: the newest of its sources
        self.assertNotIn("<lastmod></lastmod>", xml)

    def test_a_planted_future_date_is_red_and_a_page_with_no_date_has_no_lastmod(self):
        bad = lastmod_problems("<lastmod>2999-01-01</lastmod><lastmod>soon</lastmod><lastmod>2026-10-16</lastmod>", "2026-10-17")
        self.assertEqual(len(bad), 2, bad)
        xml = seo.sitemap({"https://developer.ivendnext.com/a.html": "", "https://developer.ivendnext.com/b.html": "2026-10-16"})
        self.assertIn("<loc>https://developer.ivendnext.com/a.html</loc></url>", xml)
        self.assertIn("<loc>https://developer.ivendnext.com/b.html</loc><lastmod>2026-10-16</lastmod>", xml)
        self.assertEqual(seo.newest(None, ["a"]), "")                                   # no history, no date
        self.assertEqual(seo.newest({"a": "2026-10-01", "b": "2026-10-09"}, ["a", "b", "c"]), "2026-10-09")

    def test_a_shallow_clone_gives_no_dates_and_a_deploy_build_refuses_it(self):
        import contextlib, io, subprocess
        self.assertIsNone(seo.git_dates(self.tmp))                                       # not a repository
        shallow = self.tmp / "shallow"
        done = subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-checkout", "file://" + str(build.ROOT), str(shallow)], capture_output=True)
        if done.returncode != 0:
            self.skipTest("could not make a shallow clone here: " + done.stderr.decode()[:200])
        self.assertEqual(subprocess.run(["git", "-C", str(shallow), "rev-parse", "--is-shallow-repository"], capture_output=True, text=True).stdout.strip(), "true")
        self.assertIsNone(seo.git_dates(shallow))
        kit = self.planted_kit("shallow_deploy")
        said = io.StringIO()
        with mock.patch.dict("os.environ", {"SITE_REQUIRE_OPTIONAL": "true"}), contextlib.redirect_stdout(said):
            self.assertEqual(self.build_in(kit), 1)                                      # the planted kit has no history
        self.assertIn("fetch-depth: 0", said.getvalue())                                 # refused for that reason, not for another

    def test_a_recipe_or_sample_is_dated_by_the_cards_it_serves_and_a_list_by_a_removal_too(self):
        import subprocess
        if seo.git_dates(build.ROOT) is None:
            self.skipTest("a shallow clone: no dates")
        git = lambda *paths: max(subprocess.run(["git", "-C", str(build.ROOT), "log", "-1", "--format=%cs", "--", p], capture_output=True, text=True).stdout.strip() for p in paths)
        served = catalogue_backlinks()
        xml = self.html_of("sitemap.xml")
        for recipe in ("recipes/capture", "recipes/rule_guard", "recipes/configure_no_code"):
            cards = [c.rel for c in served[recipe + ".md"]]
            self.assertTrue(cards, recipe)
            want = git(recipe + ".md", *cards)
            got = re.search(rf"<loc>https://developer.ivendnext.com/{recipe}.html</loc><lastmod>([^<]*)", xml).group(1)
            self.assertEqual(got, want, recipe)                                          # not older than the list it shows
        dates = {"needs/stock/a.md": "2026-10-01", "needs/stock/gone.md": "2026-10-09", "needs/till/b.md": "2026-10-12", "samples/s1/README.md": "2026-10-03",
                 "samples/s1/code.py": "2026-10-14"}
        self.assertEqual(seo.newest(dates, ["needs/stock/"]), "2026-10-09")               # a card deleted on the 9th dates the stock page
        self.assertEqual(seo.newest(dates, [("samples/", "README.md")]), "2026-10-03")    # a sample's code does not date the list of cards
        self.assertEqual(seo.newest(dates, ["needs/stock/a.md"]), "2026-10-01")

    def test_a_description_leaves_out_code_blocks_keeps_underscores_and_stops_at_a_list(self):
        page = "# T\n\n```markdown\nApp name: <its name>\n```\n\nSample S9 lives in samples/s9_bi_feed/ and reads tools/mcp_server/ too.\n\nIt fires at one of two events:\n\n- one\n- two\n\nNot this one.\n"
        self.assertEqual(seo.lead(page), "Sample S9 lives in samples/s9_bi_feed/ and reads tools/mcp_server/ too. Not this one.")   # the colon sentence is dropped
        self.assertEqual(seo.lead("# T\n\nA capture asks your service. It fires at one of two events:\n\n- a\n\nIt is for partners.\n"),
                         "A capture asks your service. It is for partners.")
        cut = seo.fit("Ready, with limits. " + "word " * 26 + '(the key and "the two secrets ' + "x" * 80)       # a cut leaves no bracket or quotation open
        self.assertNotIn("(", cut)
        self.assertNotIn('"', cut)

    # llms.txt and robots.txt
    def test_llms_txt_lists_the_sections_and_every_link_is_a_built_page(self):
        text = self.html_of("llms.txt")
        for head in ("Start here", "Needs", "Guide", "Recipes", "Samples", "Machine-readable"):
            self.assertIn(f"\n## {head}\n", text)
        self.assertTrue(text.startswith("# iVendNext Developers\n\n> "))
        self.assertNotIn("github.com/ivendnext-developers/partner-kit", text)             # the kit is private until Stage 2
        self.assertIn("https://developer.ivendnext.com/catalogue.json", text)
        self.assertIn("https://developer.ivendnext.com/guide/13_ai.html", text)
        links = re.findall(r"^- \[[^\]]+\]\((https://developer\.ivendnext\.com/[^)]*)\): \S", text, re.M)
        self.assertGreater(len(links), 60)
        for url in links:
            path = url.removeprefix("https://developer.ivendnext.com/")
            path = path + "index.html" if path == "" or path.endswith("/") else path
            self.assertTrue((self.out / path).is_file(), url)
        self.assertEqual(len(links), len(re.findall(r"^- \[", text, re.M)))                # every line is a link with a line of words

    def test_robots_txt_allows_everything_and_names_the_sitemap(self):
        robots = self.html_of("robots.txt")
        self.assertEqual(robots, "User-agent: *\nAllow: /\n\nSitemap: https://developer.ivendnext.com/sitemap.xml\n")
        self.assertNotIn("Disallow", robots)

    # redirects
    def redirect_build(self, name: str, pairs: str) -> tuple[int, pathlib.Path]:
        kit = self.planted_kit(name)
        table = self.tmp / (name + "_redirects.txt")
        table.write_text(pairs, "utf-8")
        with mock.patch.object(build, "REDIRECTS", table):
            return self.build_in(kit), self.tmp / (name + "_out")

    def test_a_planted_redirect_writes_a_noindex_stub_that_names_a_built_page(self):
        code, out = self.redirect_build("redirect_ok", "# a moved chapter\nguide/old_chapter.html guide/04_configure_first.html\n")
        self.assertEqual(code, 0)
        stub = (out / "guide" / "old_chapter.html").read_text("utf-8")
        self.assertIn('<link rel="canonical" href="https://developer.ivendnext.com/guide/04_configure_first.html">', stub)
        self.assertIn('<meta http-equiv="refresh" content="0; url=04_configure_first.html">', stub)
        self.assertFalse(indexable(stub))
        self.assertTrue((out / "guide" / "04_configure_first.html").is_file())                 # the new address is a built page
        self.assertNotIn("old_chapter", (out / "sitemap.xml").read_text("utf-8"))              # the old address is not listed
        self.assertEqual(check_links.check(out), [])
        self.assertEqual(seo.read_redirects(build.REDIRECTS), [])                              # the real table is empty

    def test_a_redirect_to_a_page_that_is_not_built_or_over_a_page_is_red(self):
        self.assertEqual(self.redirect_build("redirect_gone", "guide/old.html guide/no_such_page.html\n")[0], 1)
        self.assertEqual(self.redirect_build("redirect_over", "start.html build.html\n")[0], 1)
        self.assertEqual(self.redirect_build("redirect_bare", "guide/old.html\n")[0], 1)

    # the 404 page
    def test_the_404_page_has_search_the_three_ways_in_and_every_need_a_to_z_and_is_noindex(self):
        text = self.html_of("404.html")
        self.assertFalse(indexable(text))
        self.assertIn('<form class="search-page" action="/search.html" method="get" role="search">', text)
        for href in ("/needs/index.html", "/build.html", "/start.html"):
            self.assertIn(f'<a href="{href}">', text)
        cards = len(catalogue_cards())
        self.assertEqual(len(re.findall(r'<li><a href="/needs/[a-z]+/[a-z0-9-]+\.html">', text)), cards)
        self.assertIn("<h3>A</h3>", text)

    # verification tags
    def test_verification_tags_are_written_only_when_set_and_only_on_the_home_page(self):
        for out, text in page_texts(self.out, only_indexable=False).items():
            self.assertNotIn("google-site-verification", text, out)
            self.assertNotIn("msvalidate.01", text, out)
        kit = self.planted_kit("verify")
        table = self.tmp / "verify_seo.json"
        data = json.loads(build.SEO_JSON.read_text("utf-8"))
        data.update(google_site_verification="g00gle-t0ken_abc123", bing_site_verification="B1ng-t0ken_abc123")
        table.write_text(json.dumps(data), "utf-8")
        with mock.patch.object(build, "SEO_JSON", table):
            self.assertEqual(self.build_in(kit), 0)
        out = self.tmp / "verify_out"
        home = (out / "index.html").read_text("utf-8")
        self.assertIn('<meta name="google-site-verification" content="g00gle-t0ken_abc123">', home)
        self.assertIn('<meta name="msvalidate.01" content="B1ng-t0ken_abc123">', home)
        self.assertNotIn("google-site-verification", (out / "start.html").read_text("utf-8"))
        data["google_site_verification"] = "bad value<script>"                               # never a value that is not one
        table.write_text(json.dumps(data), "utf-8")
        with mock.patch.object(build, "SEO_JSON", table):
            self.assertEqual(self.build_in(kit), 1)

    # speed: a picture reserves its room
    def test_a_kit_image_in_a_page_carries_its_width_and_height(self):
        for out in ("guide/04_configure_first.html", "recipes/configure_no_code.html"):
            imgs = re.findall(r'<img src="[^"]+\.(?:gif|png)"[^>]*>', self.html_of(out))
            self.assertTrue(imgs, out)
            for tag in imgs:
                self.assertRegex(tag, r'width="\d+"')
                self.assertRegex(tag, r'height="\d+"')
        self.assertIsNotNone(seo.image_size(build.ROOT / "samples/s5_config_pack/screenshots/s5_flow.gif"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
