#!/usr/bin/env python3
"""site/test_pdfs.py — the branded PDFs (site/pdf/build_pdfs.py) and each of their checks, shown able to fail.

    CHROME=/path/to/chrome python3 site/test_pdfs.py        # needs headless Chrome, as the build does; run in the Site workflow

Each planted fault turns its check red; the real PDFs, built from the kit, pass every check."""
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent / "pdf"))
import build_pdfs  # noqa: E402

catalogue = build_pdfs.catalogue


class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.stage = cls.tmp / "stage"
        cls.stage.mkdir()
        build_pdfs.stage(cls.stage)
        cls.out = cls.tmp / "out"
        assert build_pdfs.build_pdfs(cls.out) == 0
        cls.form = (cls.out / "downloads" / "blueprint_form.pdf").read_bytes()
        cls.guide = (cls.out / "downloads" / "blueprint_how_to_fill.pdf").read_bytes()
        cls.example = (cls.out / "downloads" / "blueprint_example.pdf").read_bytes()
        cls.ladder = (cls.out / "downloads" / "ladder_and_four_rules.pdf").read_bytes()
        cls.glance = (cls.out / "downloads" / "needs_at_a_glance.pdf").read_bytes()
        cls.howitworks = (cls.out / "downloads" / "how_ivendnext_apps_work.pdf").read_bytes()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def planted(self, rel: str, edit) -> pathlib.Path:
        """A copy of the kit (every entry linked) with the file `rel` copied and edited, for a test to point build.ROOT at."""
        kit = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        for entry in build_pdfs.build.ROOT.iterdir():
            if entry.name != rel.split("/")[0] and entry.name != ".git":
                (kit / entry.name).symlink_to(entry)
        shutil.copytree(build_pdfs.build.ROOT / rel.split("/")[0], kit / rel.split("/")[0])
        f = kit / rel
        f.write_text(edit(f.read_text("utf-8")), "utf-8")
        return kit

    def pdf_of(self, body: str, cls: str = "") -> bytes:
        return build_pdfs.print_pdf(build_pdfs.page("A test", body, cls), self.stage)

    def pages(self, data: bytes) -> int:
        return sum(1 for d, _ in build_pdfs.objects(data) if re.search(rb"/Type\s*/Page(?![A-Za-z])", build_pdfs.names(d)))

    # the real PDFs
    def test_the_built_pdfs_pass_every_check_within_their_budgets(self):
        self.assertEqual(build_pdfs.pdf_problems(self.form, 4, landscape=1), [])
        self.assertEqual(build_pdfs.pdf_problems(self.guide, 1, exact=True), [])
        self.assertEqual(build_pdfs.pdf_problems(self.example, 5, landscape=1), [])
        self.assertEqual(build_pdfs.pdf_problems(self.ladder, 2, exact=True), [])
        self.assertEqual(build_pdfs.pdf_problems(self.glance, 6), [])
        self.assertLessEqual(self.pages(self.form), 4)
        self.assertEqual(self.pages(self.guide), 1)
        self.assertEqual(self.pages(self.ladder), 2)
        self.assertLessEqual(self.pages(self.glance), 6)
        self.assertEqual(build_pdfs.pdf_problems(self.howitworks, 10), [])
        self.assertLessEqual(self.pages(self.howitworks), 10)                                     # measured 2026-10-28: 10 pages
        for data in (self.form, self.guide, self.example, self.ladder, self.glance):
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertTrue(data.rstrip().endswith(b"%%EOF"))
            self.assertIn(b"/URI", data)                       # the link check has links to read, so it is not vacuous
            self.assertRegex(data, rb"/FontName\s*/[A-Z]{6}\+Inter")

    def test_the_form_shows_every_status_word_and_a_renamed_status_is_red(self):
        form = build_pdfs.form_body([])
        self.assertEqual(build_pdfs.missing_statuses(form, catalogue.STATUSES), [])
        renamed = dict(catalogue.STATUSES, **{"ready-with-limits": "Ready, within limits"})
        self.assertEqual(build_pdfs.missing_statuses(form, renamed), ["Ready, within limits"])
        self.assertEqual(build_pdfs.missing_statuses(build_pdfs.form_body([], renamed), renamed), [])   # the boxes follow the catalogue

    def test_section_b_of_the_template_is_the_header_needs_py_prints(self):
        _, sections = build_pdfs.parse_template((build_pdfs.build.ROOT / build_pdfs.TEMPLATE).read_text("utf-8"))
        b = next(s for s in sections if s["letter"] == "b")
        self.assertEqual("| " + " | ".join(b["rows"][0]) + " |", catalogue.BLUEPRINT_HEAD.split("\n")[0])
        self.assertEqual([s["letter"] for s in sections], list("abcdef"))

    def test_a_template_table_whose_columns_change_fails_the_build(self):
        errors: list = []
        sec = {"letter": "f", "title": "(f) Risks", "hints": [], "rows": [["#", "Risk", "Touches", "Settle", "Who", "New"], ["1", "", "", "", "", ""]]}
        self.assertEqual(build_pdfs.form_table(sec, catalogue.STATUSES, errors), "")
        self.assertEqual(len(errors), 1)

    # page budget
    def test_a_two_page_one_pager_is_red(self):
        long = build_pdfs.guide_body([]) + "".join(f"<p>A planted paragraph, number {i}, that makes the page too long.</p>" for i in range(40))
        problems = build_pdfs.pdf_problems(self.pdf_of(long, "guide"), 1, exact=True)
        self.assertTrue(any("budget is exactly 1" in p for p in problems), problems)

    # the ladder and the four rules (row PDFMORE): one section to a page, so a section that outgrows its page fails
    def test_a_paragraph_planted_inside_the_ladder_overflows_its_page_and_is_red(self):
        planted = " ".join(f"A planted sentence, number {i}, inside the ladder's own section." for i in range(60))
        kit = self.planted(build_pdfs.LADDER, lambda t: t.replace("**Combine rungs.**", planted + "\n\n**Combine rungs.**", 1))
        real = build_pdfs.build.ROOT
        build_pdfs.build.ROOT = kit
        try:
            body = build_pdfs.ladder_body([])
        finally:
            build_pdfs.build.ROOT = real
        self.assertIn("number 59, inside the ladder", body.split('class="sheet rules"')[0])      # read: it is inside the section
        problems = build_pdfs.pdf_problems(self.pdf_of(body), 2, exact=True)
        self.assertTrue(any("budget is exactly 2" in p for p in problems), problems)
        self.assertEqual(build_pdfs.pdf_problems(self.pdf_of(build_pdfs.ladder_body([])), 2, exact=True), [])

    # needs at a glance: every card once, no row without a card
    def test_needs_at_a_glance_lists_every_card_once_and_a_missing_twice_or_unknown_one_is_red(self):
        cards = catalogue.load(build_pdfs.build.ROOT)
        body = build_pdfs.glance_body([])
        self.assertEqual(build_pdfs.glance_problems(body, cards), [])
        self.assertEqual(len(re.findall(r'<tr data-id=', body)), len(cards))
        extra = catalogue.Card.__new__(catalogue.Card)
        extra.meta = {"id": "a-planted-card"}
        self.assertEqual(build_pdfs.glance_problems(body, cards + [extra]), ["the card a-planted-card is not listed"])
        row = re.search(r'<tr data-id="line-quantity-cap">.*?</tr>', body).group()
        self.assertEqual(build_pdfs.glance_problems(body.replace(row, row + row), cards), ["the card line-quantity-cap is listed 2 times"])
        self.assertEqual(build_pdfs.glance_problems(body.replace(row, row.replace("line-quantity-cap", "no-such-card")), cards),
                         ["the card line-quantity-cap is not listed", "the row no-such-card names no card"])

    # the filled example (row PDFMORE): the form's own layout, its answers printed and its boxes ticked
    def test_a_choice_cell_ticks_on_its_first_word_and_a_status_only_on_a_verdict_word(self):
        on = lambda html: re.findall(r'<span class="tick on"></span>([^<]+)', html)
        statuses = list(catalogue.STATUSES.values())
        self.assertEqual(on(build_pdfs.choice("Ready, with limits", statuses, True, "x", [])), ["Ready, with limits"])
        self.assertEqual(on(build_pdfs.choice("Ready", statuses, True, "x", [])), ["Ready"])
        cell = build_pdfs.choice("estimated from last year", ["counted", "estimated"], False, "x", [])
        self.assertEqual(on(cell), ["estimated"])
        self.assertIn('<span class="note">from last year</span>', cell)
        self.assertEqual(on(build_pdfs.choice("on", ["On", "Off"], False, "x", [])), ["On"])
        self.assertEqual(on(build_pdfs.choice("Off", ["On", "Off"], False, "x", [])), ["Off"])
        self.assertEqual(on(build_pdfs.choice("", ["On", "Off"], False, "x", [])), [])               # the blank form's
        errors: list = []
        build_pdfs.choice("Ready with limits", statuses, True, "row 1, Status", errors)               # not a verdict word
        build_pdfs.choice("perhaps", ["On", "Off"], False, "row 2, On / off", errors)
        self.assertEqual(len(errors), 2, errors)

    def test_an_example_status_that_is_not_a_verdict_word_fails_the_build(self):
        body = build_pdfs.example_body(errors := [])
        self.assertEqual(errors, [])
        self.assertEqual(build_pdfs.missing_statuses(body, catalogue.STATUSES), [])
        kit = self.planted(build_pdfs.EXAMPLE, lambda t: t.replace("| Ready | Configure |", "| Ready, mostly | Configure |", 1))
        real = build_pdfs.build.ROOT
        build_pdfs.build.ROOT = kit
        try:
            build_pdfs.example_body(errors := [])
        finally:
            build_pdfs.build.ROOT = real
        self.assertTrue(any("'Ready, mostly' ticks none of the boxes" in e for e in errors), errors)

    def test_the_example_prints_its_answers_and_one_without_them_is_red(self):
        body = build_pdfs.example_body([])
        self.assertEqual(build_pdfs.missing_answers(body), [])
        self.assertIn("Blueprint example — Corvane Mobile", body)
        blank = build_pdfs.field_rows
        with mock.patch.object(build_pdfs, "field_rows", lambda fields, project="", errors=None: blank([[f[0]] for f in fields])):
            stripped = build_pdfs.example_body([])
        missing = build_pdfs.missing_answers(stripped)
        self.assertTrue(any("2026-10-16" in m for m in missing) and any("is not ticked" in m for m in missing), missing)
        self.assertIn("the Project row: 'Corvane Mobile'", missing)             # the band's name alone does not count

    def test_the_example_over_its_measured_budget_is_red(self):
        doc = next(d for d in build_pdfs.DOCS if d.name == "blueprint_example.pdf")
        self.assertEqual((doc.pages, doc.landscape, doc.exact), (5, 1, False))               # measured 2026-10-16: 5 pages
        long = build_pdfs.example_body([]) + "".join(f"<p>A planted paragraph, number {i}, past the budget.</p>" for i in range(60))
        problems = build_pdfs.pdf_problems(self.pdf_of(long), doc.pages, landscape=1)
        self.assertTrue(any("budget is at most 5" in p for p in problems), problems)

    # what a PDF may hold
    def test_a_planted_javascript_action_is_red_however_its_name_is_written(self):
        for planted, word in ((b"/OpenAction << /S /JavaScript /JS (app.alert\\(1\\)) >>", "/JavaScript"),
                              (b"/OpenAction << /S /Java#53cript /J#53 (x) >>", "/JavaScript"),
                              (b"/OpenAction << /S /Launch /F (calc.exe) >>", "/Launch"),
                              (b"/Names << /EmbeddedFiles << >> >> /AF [<< /Type /EmbeddedFile >>]", "/EmbeddedFile")):
            data = self.guide.replace(b"/Type /Catalog", b"/Type /Catalog " + planted, 1)
            self.assertNotEqual(data, self.guide)
            self.assertIn(f"it holds {word}", build_pdfs.pdf_problems(data, 1, exact=True), planted)

    def test_a_font_that_is_not_embedded_is_red(self):
        data = self.guide.replace(b"/FontFile2", b"/FontFileZ", 1)
        self.assertTrue(any("is not embedded" in p for p in build_pdfs.pdf_problems(data, 1, exact=True)))
        plain = self.guide.replace(b"/Type /Catalog", b"/Type /Catalog /X << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", 1)
        self.assertTrue(any("Helvetica (Type1) is not an embedded Inter" in p for p in build_pdfs.pdf_problems(plain, 1, exact=True)))

    def test_an_embedded_font_that_is_not_inter_is_red(self):
        problems = build_pdfs.pdf_problems(self.pdf_of('<p style="font-family: serif">A system serif, not Inter.</p>'), 1)
        self.assertTrue(any("is not Inter" in p for p in problems), problems)
        self.assertEqual(build_pdfs.pdf_problems(self.pdf_of("<p>Inter, as everywhere.</p>"), 1), [])

    def test_a_link_to_another_host_or_to_a_file_is_red_and_ours_are_green(self):
        bad = self.pdf_of('<p><a href="https://example.com/x">another host</a> · <a href="other.html">a relative link</a> · '
                          '<a href="http://developer.ivendnext.com/">not https</a> · <a href="https://github.com/someone-else/kit">another org</a></p>')
        problems = " ".join(build_pdfs.pdf_problems(bad, 1))
        for uri in ("https://example.com/x", "file:", "http://developer.ivendnext.com/", "https://github.com/someone-else/kit"):
            self.assertIn(f"it links {uri}", problems)
        good = self.pdf_of('<p><a href="https://developer.ivendnext.com/kit/blueprint.html">ours</a> · '
                           '<a href="https://github.com/ivendnext-developers/partner-kit">the kit</a> · '
                           '<a href="https://github.com/ivendnext-developers">the organisation</a></p>')
        self.assertEqual(build_pdfs.pdf_problems(good, 1), [])

    def test_a_form_whose_landscape_page_is_not_honoured_is_red(self):
        self.assertEqual([s for s in build_pdfs.page_sizes(self.form) if s[0] > s[1]], [(842, 595)])
        css = (self.stage / "print.css").read_text("utf-8")
        try:                                                      # the named page dropped: Chrome shrinks (d) onto a portrait page
            (self.stage / "print.css").write_text(css.replace(".wide { page: wide; }", ""), "utf-8")
            shrunk = build_pdfs.print_pdf(build_pdfs.page("Project blueprint", build_pdfs.form_body([])), self.stage)
        finally:
            (self.stage / "print.css").write_text(css, "utf-8")
        self.assertIn("it has 0 landscape pages, not 1", build_pdfs.pdf_problems(shrunk, 4, landscape=1))
        self.assertIn("it has 1 landscape pages, not 0", build_pdfs.pdf_problems(self.form, 4))

    def test_a_page_that_fetches_a_file_from_elsewhere_is_red(self):
        self.assertEqual(build_pdfs.fetched(build_pdfs.page("A test", build_pdfs.guide_body([]))), [])
        self.assertEqual(build_pdfs.fetched('<img src="https://developer.ivendnext.com/x.png"><p style="background:url(//cdn.example/x.png)">'),
                         ["https://developer.ivendnext.com/x.png", "//cdn.example/x.png"])
        self.assertEqual(build_pdfs.fetched('<img src="logo-band.svg">'), [])

    def test_a_cut_short_pdf_or_one_that_is_not_a_pdf_is_red(self):
        self.assertIn("it does not end with %%EOF (cut short)", build_pdfs.pdf_problems(self.guide[:-40], 1, exact=True))
        self.assertIn("it does not start with %PDF-", build_pdfs.pdf_problems(b"<html>" + self.guide, 1, exact=True))

    # the box measure
    def test_a_table_wider_than_the_page_is_red_portrait_and_landscape(self):
        past = lambda body: any("runs past the content edge" in p for p in build_pdfs.measure(build_pdfs.page("A test", body), self.stage))
        self.assertTrue(past('<table style="width:200mm;table-layout:fixed"><tr><td>a table wider than 170 mm</td></tr></table>'))
        self.assertTrue(past('<section class="wide"><table style="width:270mm"><tr><td>wider than 257 mm</td></tr></table></section>'))
        fits = '<section class="wide"><table style="width:250mm"><tr><td>within 257 mm</td></tr></table></section>'
        self.assertEqual(build_pdfs.measure(build_pdfs.page("A test", fits), self.stage), [])

    def test_content_wider_than_its_cell_is_red(self):
        cell = ('<table style="table-layout:fixed;width:100mm"><colgroup><col style="width:20mm"><col></colgroup><tr>'
                '<td><span style="white-space:nowrap">a phrase that cannot wrap in twenty millimetres</span></td><td></td></tr></table>')
        self.assertTrue(any("wider than its cell" in p for p in build_pdfs.measure(build_pdfs.page("A test", cell), self.stage)))

    def test_the_real_pages_measure_clean(self):
        for doc in build_pdfs.DOCS:
            self.assertEqual(build_pdfs.measure(build_pdfs.page(doc.title, doc.make([]), doc.cls), self.stage), [], doc.name)

    # the words
    def test_the_pdfs_words_pass_the_kits_word_rules_and_a_planted_name_is_red(self):
        for doc in build_pdfs.DOCS:
            self.assertEqual(build_pdfs.word_problems(build_pdfs.page(doc.title, doc.make([]), doc.cls)), [], doc.name)
        upstream = "Fra" + "ppe"                                   # never written whole in a kit file
        self.assertTrue(build_pdfs.word_problems(f"<p>Built on {upstream}.</p>"))
        self.assertTrue(build_pdfs.word_problems("<p>Ask for a new point.</p>"))
        self.assertEqual(build_pdfs.word_problems("<p>Ask for a new extension point.</p>"), [])

    # Chrome
    def test_how_apps_work_draws_every_picture_of_chapter_1a_inline_and_a_linked_one_is_red(self):
        names = build_pdfs.chapter_pictures(build_pdfs.HOWITWORKS)
        self.assertGreaterEqual(len(names), 7)                                              # the six of HOWITWORKS-A and where-your-app-runs
        errors: list = []
        body = build_pdfs.howitworks_body(errors)
        self.assertEqual(errors, [])
        self.assertEqual(body.count("<svg "), len(names))
        self.assertNotIn("guide/img/", body)
        self.assertEqual(build_pdfs.fetched(build_pdfs.page("How iVendNext apps work", body)), [])
        linked = body + f'<img src="{build_pdfs.BASE}guide/img/{names[0]}" alt="">'      # a picture left as a link would be fetched
        self.assertEqual(build_pdfs.fetched(build_pdfs.page("How iVendNext apps work", linked)), [f"{build_pdfs.BASE}guide/img/{names[0]}"])

    def test_no_chrome_fails_and_says_how_to_set_it(self):
        with mock.patch.dict("os.environ", {"CHROME": "/no/such/chrome"}):
            with self.assertRaises(SystemExit) as caught:
                build_pdfs.chrome()
        self.assertIn("Set CHROME", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
