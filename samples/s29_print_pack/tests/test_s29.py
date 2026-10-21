"""S29's laptop tests: the two manifests are the files' build and pass the checker; a template reads only the invoice it is
given; the branch prints each customer's layout and a plain one for a stranger (needs jinja2: skipped without it, and said);
the price list holds every item once, with its picture or a reported placeholder, and nothing from outside.

    python3 -m unittest discover -s samples/s29_print_pack/tests -p 'test_*.py'
"""
import csv
import io
import json
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SAMPLE))
sys.path.insert(0, str(SAMPLE.parents[1] / "tools" / "manifest"))
import build  # noqa: E402
import catalogue as C  # noqa: E402
import validate  # noqa: E402
from fakes import JPG, PNG, FakeShop, Row, invoice, item, price  # noqa: E402

try:
    import jinja2
except ImportError:  # the kit's CI installs it; a laptop without it skips the rendering tests and says so
    if os.environ.get("S29_REQUIRE_JINJA"):  # CI sets this: a skipped template test must not read as green
        raise
    jinja2 = None

NEED_JINJA = unittest.skipUnless(jinja2, "jinja2 is not installed: the rendering tests did not run")
CUSTOMERS = build.customers()
A, B, C_ = CUSTOMERS["layout_a"], CUSTOMERS["layout_b"], CUSTOMERS["layout_c"]
MARK = {"a": "Tax Invoice", "b": "COMMERCIAL INVOICE", "c": "Your order", "plain": "Invoice SINV-0001"}


def render(html, doc):
    return jinja2.Environment(autoescape=False).from_string(html).render(doc=doc)


def which(out):
    return [k for k, m in MARK.items() if m in out]


class Manifests(unittest.TestCase):
    def test_both_manifests_are_the_build_of_the_files_and_pass_the_checker(self):
        for fname, built in (("branch_manifest.json", build.build_branch()), ("each_manifest.json", build.build_each())):
            self.assertEqual(json.loads((SAMPLE / fname).read_text(encoding="utf-8")), built, fname)
            self.assertEqual(validate.validate(built), [], fname)

    def test_the_branch_is_one_format_and_each_is_four_on_the_sales_invoice(self):
        b, e = build.build_branch()["print_formats"], build.build_each()["print_formats"]
        self.assertEqual((len(b), len(e)), (1, 4))
        self.assertTrue(all(p["doc_type"] == "Sales Invoice" and p["name"].startswith("PP PRT ") for p in b + e))

    def test_the_checker_refuses_a_script_a_frame_and_an_outside_address(self):
        for plant in ("<script>x()</script>", "<iframe src=\"a\"></iframe>", "<img src=\"https://example.com/x.png\">",
                      "<div onclick=\"x()\">"):
            m = build.build_branch()
            m["print_formats"][0]["html"] += plant
            self.assertTrue(validate.validate(m), plant)

    def test_customers_json_is_checked(self):
        for bad in ({"layout_a": " A", "layout_b": "B", "layout_c": "C"}, {"layout_a": "", "layout_b": "B", "layout_c": "C"},
                    {"layout_a": "X", "layout_b": "X", "layout_c": "C"},
                    {"layout_a": "A", "layout_b": "B"}):
            with self.subTest(bad=bad):
                orig = build._read
                build._read = lambda p, orig=orig, bad=bad: json.dumps(bad) if p == "customers.json" else orig(p)
                try:
                    with self.assertRaises(SystemExit):
                        build.customers()
                finally:
                    build._read = orig


class Templates(unittest.TestCase):
    def test_a_template_reads_only_the_invoice_it_is_given(self):
        """Every {{ }} and {% %} expression starts from doc, an item or tax row, or the loop: no row reader, no upstream name."""
        for p in sorted((SAMPLE / "layouts").glob("*.html")):
            txt = re.sub(r"\{#.*?#\}", "", p.read_text(encoding="utf-8"), flags=re.S)
            for expr in re.findall(r"\{[{%]-?(.*?)-?[}%]\}", txt, flags=re.S):
                roots = set(re.findall(r"(?<![\w.\"'])([A-Za-z_]\w*)", re.sub(r"\"[^\"]*\"|'[^']*'", "", expr)))
                roots -= {"if", "elif", "else", "endif", "for", "endfor", "in", "or", "and", "not", "is", "none", "None", "set"}
                self.assertLessEqual(roots, {"doc", "item", "t", "loop"}, f"{p.name}: {expr.strip()}")
            self.assertNotRegex(txt, r"get_all|get_value|get_doc|\.db\.|fr" r"appe|erp" r"next", p.name)  # the words are split so this file holds none of them

    def test_every_amount_is_the_documents_own_formatted_value(self):
        for p in sorted((SAMPLE / "layouts").glob("*.html")):
            txt = p.read_text(encoding="utf-8")
            self.assertIn('doc.get_formatted("grand_total")', txt, p.name)
            self.assertNotRegex(txt, r"\*|fmt_money|round\(", p.name)  # nothing is worked out here

    def test_each_layout_has_a_header_a_column_set_and_a_footer_of_its_own(self):
        heads = {}
        for k in ("layout_a", "layout_b", "layout_c", "layout_plain"):
            txt = (SAMPLE / "layouts" / f"{k}.html").read_text(encoding="utf-8")
            self.assertRegex(txt, r"<thead>|<th", k)
            cols = tuple(re.findall(r"<th[^>]*>([^<]+)</th>", txt))
            heads[k] = cols
        self.assertEqual(len(set(heads.values())), 4, heads)  # four different column sets

    def test_a_logo_is_embedded_never_an_outside_address(self):
        for m in (build.build_branch(), build.build_each()):
            for p in m["print_formats"]:
                if "Plain" not in p["name"] and "Branch" not in p["name"]:
                    self.assertIn("data:image/png;base64,", p["html"])
                self.assertNotRegex(p["html"], r"https?://|\bsrc=\"/", p["name"])



class PriceListFormat(unittest.TestCase):
    """The print format on the Price List (POS build 2.0.0.654 on): its rows through ivn_rows, each photo through ivn_value."""
    html = build.build_price_list()["print_formats"][0]["html"]

    def test_the_manifest_is_the_build_of_the_file_and_passes_the_checker_with_no_warning(self):
        built = build.build_price_list()
        self.assertEqual(json.loads((SAMPLE / "price_list_manifest.json").read_text(encoding="utf-8")), built)
        self.assertEqual((validate.validate(built), validate.warnings(built)), ([], []))
        self.assertEqual([(p["name"], p["doc_type"]) for p in built["print_formats"]],
                         [("PP PLR Price List with Photos", "Price List")])

    def test_it_reads_other_records_only_through_the_two_readers(self):
        txt = re.sub(r"\{#.*?#\}", "", self.html, flags=re.S)
        for expr in re.findall(r"\{[{%]-?(.*?)-?[}%]\}", txt, flags=re.S):
            roots = set(re.findall(r"(?<![\w.\"'])([A-Za-z_]\w*)", re.sub(r"\"[^\"]*\"|'[^']*'", "", expr)))
            roots -= {"if", "endif", "for", "endfor", "in", "set", "asc"}
            self.assertLessEqual(roots, {"doc", "r", "photo", "start", "ivn_rows", "ivn_value", "filters", "fields",
                                         "order_by", "limit", "name", "field"}, expr.strip())
        self.assertNotRegex(txt, r"get_all|get_value|get_doc|\.db\.|fr" r"appe|erp" r"next")

    @NEED_JINJA
    def test_every_general_price_prints_with_its_photo_page_by_page(self):
        prices = [{"item_code": f"IT-{i:04d}", "item_name": f"Item {i}", "price_list_rate": i, "uom": "Nos"} for i in range(450)]
        calls = []

        def ivn_rows(dt, filters=None, fields=None, order_by=None, limit=50, start=0):
            calls.append((dt, dict(filters), start, limit))
            return [type("R", (), p) for p in prices[start:start + limit]]

        def ivn_value(dt, name=None, field=None):
            return "/files/it-0001.png" if (dt, name, field) == ("Item", "IT-0001", "image") else None

        doc = {"name": "Distributor A", "price_list_name": "Distributor A", "currency": "ZAR", "selling": 1, "buying": 0}
        out = jinja2.Environment(autoescape=True).from_string(self.html).render(doc=doc, ivn_rows=ivn_rows, ivn_value=ivn_value)
        self.assertEqual(out.count("<tr style=\"border-bottom"), 450)
        self.assertEqual(out.count("<img "), 1)
        self.assertIn('src="/files/it-0001.png"', out)
        self.assertEqual([c[2] for c in calls], [0, 200, 400, 600, 800])
        self.assertEqual({c[3] for c in calls}, {200})
        self.assertEqual(calls[0][1], {"price_list": "Distributor A", "customer": ["is", "not set"], "batch_no": ["is", "not set"]})


@NEED_JINJA
class Branch(unittest.TestCase):
    html = None

    @classmethod
    def setUpClass(cls):
        cls.html = build.branch_html()

    def test_each_customer_gets_their_own_layout(self):
        self.assertEqual(which(render(self.html, invoice(A))), ["a"])
        self.assertEqual(which(render(self.html, invoice(B))), ["b"])
        self.assertEqual(which(render(self.html, invoice(C_, po_no="PO-9"))), ["c"])

    def test_the_three_outputs_differ(self):
        outs = {render(self.html, invoice(n, customer_name="Same")) for n in (A, B, C_)}  # only the layout can differ
        self.assertEqual(len(outs), 3)

    def test_a_stranger_gets_the_plain_layout_not_a_blank_page(self):
        out = render(self.html, invoice("Somebody Else"))
        self.assertEqual(which(out), ["plain"])
        self.assertIn("115.00", out)
        self.assertGreater(len(out.strip()), 200)

    def test_the_invoice_own_figures_are_printed(self):
        out = render(self.html, invoice(A))
        for want in ("SINV-0001", "Demo Retail", "TAX-1", "Phone case", "115.00", "100.00", "15.00"):
            self.assertIn(want, out)

    def test_a_customer_named_with_quotes_braces_and_signs_still_matches_itself(self):
        orig = build._read
        for name in ('Smith & Co #2', '50% Off "Ltd"', 'a %} b {{ c }}', "back\\slash", 'x" %}{{ 7*7 }}{% if "', "Zoë é 店"):
            cust = {"layout_a": name, "layout_b": "B", "layout_c": "C"}
            build._read = lambda p, orig=orig, cust=cust: json.dumps(cust) if p == "customers.json" else orig(p)
            try:
                html = build.branch_html()
            finally:
                build._read = orig
            self.assertEqual(which(render(html, invoice(name))), ["a"], name)
            self.assertEqual(which(render(html, invoice("B"))), ["b"], name)

    def test_every_layout_prints_the_tax_so_the_lines_add_up_to_the_total(self):
        """The layout a stranger gets becomes the shop's invoice once the branch is the default: it must carry the tax."""
        doc = lambda n: invoice(n, taxes=[Row(description="VAT 15%", tax_amount=13.0), Row(description="Levy", tax_amount=2.0)])
        for name in (A, B, C_, "Somebody Else"):
            out = render(self.html, doc(name))
            for want in ("15.00", "115.00"):  # the tax and the total
                self.assertIn(want, out, name)
        for name in (B, C_, "Somebody Else"):  # the layouts that list each tax line (A prints the one tax figure)
            out = render(self.html, doc(name))
            for want in ("VAT 15%", "13.00", "Levy", "2.00"):
                self.assertIn(want, out, name)
        self.assertIn("Tax no. TAX-1", render(self.html, doc("Somebody Else")))  # the company's tax number
        self.assertIn("Tax no. TAX-9", render(self.html, invoice("Somebody Else", tax_id="TAX-9")))  # and the customer's

    def test_the_each_formats_print_the_same_layouts(self):
        by = {p["name"]: p["html"] for p in build.build_each()["print_formats"]}
        self.assertEqual(which(render(by["PP PRT Invoice A"], invoice(A))), ["a"])
        self.assertEqual(which(render(by["PP PRT Invoice B"], invoice(A))), ["b"])  # the format, not the customer, decides
        self.assertEqual(which(render(by["PP PRT Invoice Plain"], invoice(A))), ["plain"])

    def test_a_blank_field_prints_nothing_wrong(self):
        out = render(self.html, invoice(B, terms=None, address_display=None, territory=None))
        self.assertNotIn("None", out)


class Catalogue(unittest.TestCase):
    def shop(self, **kw):
        prices = [price("PH-1", 100), price("PH-2", 250.5), price("CB-1", 9)]
        items = [item("PH-1", image="/files/ph1.png"), item("PH-2", image="/files/ph2.jpg"), item("CB-1", "Cables", image="/files/cb.png")]
        files = {"/files/ph1.png": PNG, "/files/ph2.jpg": JPG, "/files/cb.png": PNG}
        return FakeShop(kw.get("prices", prices), kw.get("items", items), kw.get("files", files))

    def cat(self, shop, **kw):
        return C.build(shop, "WS", "2026-10-16", **kw)

    def test_every_item_of_the_list_is_there_once_with_one_picture(self):
        cat = self.cat(self.shop())
        self.assertEqual([r["code"] for r in cat["rows"]], ["CB-1", "PH-1", "PH-2"])
        out = C.render_html(cat["rows"], "A Distributor", "Wholesale", "2026-10-16")
        self.assertEqual(out.count("<img "), 3)
        self.assertEqual(out.count("data:image/"), 3)
        self.assertEqual(cat["report"]["with_picture"], 3)
        self.assertEqual(cat["report"]["without_picture"], [])

    def test_an_item_with_no_picture_gets_a_placeholder_and_is_reported(self):
        shop = self.shop(items=[item("PH-1"), item("PH-2", image="/files/ph2.jpg"), item("CB-1", "Cables", image="/files/cb.png")])
        cat = self.cat(shop)
        out = C.render_html(cat["rows"], "D", "L", "2026-10-16")
        self.assertEqual(out.count("<img "), 2)
        self.assertIn("No photo", out)
        self.assertEqual(cat["report"]["without_picture"], [{"item": "PH-1", "why": "no picture on the item"}])

    def test_a_picture_kept_outside_the_shop_is_never_fetched_or_printed(self):
        shop = self.shop(items=[item("PH-1", image="https://example.com/x.png"), item("PH-2", image="//example.com/y.png"),
                                item("CB-1", "Cables", image="/files/cb.png")])
        cat = self.cat(shop)
        self.assertEqual(shop.asked, ["/files/cb.png"])
        out = C.render_html(cat["rows"], "D", "L", "2026-10-16")
        self.assertNotRegex(out, r"example\.com")
        self.assertEqual({m["why"] for m in cat["report"]["without_picture"]}, {"the picture is kept outside the shop"})

    def test_a_page_has_no_outside_address_and_no_script(self):
        out = C.render_html(self.cat(self.shop())["rows"], "D", "L", "2026-10-16")
        self.assertNotRegex(out, r"https?:|(?<![A-Za-z0-9+/=])//[A-Za-z]|<script|\bon[a-z]+=|<link|@import|url\(")
        self.assertIn("@page{size:A4", out)

    def test_a_picture_that_is_not_a_picture_or_too_big_is_a_placeholder(self):
        svg = b"<svg onload='x()'></svg>"
        files = {"/files/ph1.png": svg, "/files/ph2.jpg": JPG + b"\x00" * 2048, "/files/cb.png": PNG}
        cat = self.cat(self.shop(files=files), max_kb=1)
        self.assertEqual(cat["report"]["with_picture"], 1)
        self.assertEqual({m["item"]: m["why"] for m in cat["report"]["without_picture"]},
                         {"PH-1": "the picture is not a PNG, JPEG, GIF or WebP", "PH-2": "the picture is over 1 kB"})
        self.assertNotIn("svg", C.render_html(cat["rows"], "D", "L", "2026-10-16"))

    def test_one_section_per_item_group(self):
        out = C.render_html(self.cat(self.shop())["rows"], "D", "L", "2026-10-16")
        self.assertEqual(re.findall(r"<h2>([^<]+)</h2>", out), ["Cables", "Phones"])
        self.assertEqual(out.count("<div class=\"grid\">"), 2)
        self.assertEqual(out.count("</div></body>"), 1)

    def test_only_general_prices_valid_today_and_the_later_start_wins(self):
        prices = [price("PH-1", 100), price("PH-1", 90, customer="Someone", valid_from="2026-10-01"), price("PH-2", 1, valid_upto="2026-10-15"),
                  price("PH-2", 2, valid_from="2026-10-17"), price("CB-1", 5, valid_from="2026-01-01"),
                  price("CB-1", 6, valid_from="2026-09-01"), price("PH-3", 7, supplier="S"), price("PH-4", 8, batch_no="B")]
        items = [item("PH-1"), item("PH-2"), item("CB-1", "Cables"), item("PH-3"), item("PH-4")]
        cat = self.cat(self.shop(prices=prices, items=items))
        self.assertEqual({r["code"]: r["rate"] for r in cat["rows"]}, {"PH-1": "100.00", "CB-1": "6.00"})

    def test_a_name_is_escaped(self):
        shop = self.shop(items=[item("PH-1", name="<b>x</b> & \"y\"", image="/files/ph1.png")], prices=[price("PH-1", 1)])
        out = C.render_html(self.cat(shop)["rows"], "A <i>D</i>", "L", "2026-10-16")
        self.assertNotIn("<b>x", out)
        self.assertNotIn("<i>D", out)
        self.assertIn("&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;", out)

    def test_the_csv_has_every_item_and_does_not_run_as_a_formula(self):
        shop = self.shop(items=[item("PH-1", name="=HYPERLINK(1)", image="/files/ph1.png"), item("PH-2"), item("CB-1", "Cables")])
        rows = list(csv.reader(io.StringIO(C.render_csv(self.cat(shop)["rows"]))))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][:3], ["Group", "Item code", "Item name"])
        self.assertIn("'=HYPERLINK(1)", [r[2] for r in rows])
        self.assertEqual(sorted(r[6] for r in rows[1:]), ["no", "no", "yes"])
        self.assertEqual({r[1]: r[5] for r in rows[1:]}, {"PH-1": "100.00", "PH-2": "250.50", "CB-1": "9.00"})  # numbers, no thousands comma
        big = self.cat(self.shop(prices=[price("PH-1", 1234567.5)]))["rows"]
        self.assertEqual(list(csv.reader(io.StringIO(C.render_csv(big))))[1][5], "1234567.50")

    def test_a_rate_prints_with_the_decimals_it_is_stored_with_and_no_float_noise(self):
        self.assertEqual([C.money(v) for v in (100, 250.5, "1234.567", 0, "0.1", 0.30000000000000004, 33.333333333)],
                         ["100.00", "250.50", "1,234.567", "0.00", "0.10", "0.30", "33.333333333"])

    def test_a_photo_the_shop_will_not_give_is_a_placeholder_and_the_run_goes_on(self):
        files = {"/files/ph1.png": C.Unreadable("the shop answered HTTP 404"), "/files/ph2.jpg": JPG, "/files/cb.png": PNG}
        cat = self.cat(self.shop(files=files))
        self.assertEqual(cat["report"]["with_picture"], 2)
        self.assertEqual(cat["report"]["without_picture"],
                         [{"item": "PH-1", "why": "the picture could not be read: the shop answered HTTP 404"}])

    def test_a_price_whose_item_the_key_cannot_read_is_left_out_and_said(self):
        cat = self.cat(self.shop(items=[item("PH-2", image="/files/ph2.jpg"), item("CB-1", "Cables", image="/files/cb.png")]))
        self.assertEqual([r["code"] for r in cat["rows"]], ["CB-1", "PH-2"])
        self.assertEqual(cat["report"]["item_not_readable"], ["PH-1"])
        self.assertNotIn("PH-1", [m["item"] for m in cat["report"]["without_picture"]])

    def test_a_disabled_item_is_left_out_and_listed(self):
        shop = self.shop(items=[item("PH-1", image="/files/ph1.png", disabled=1), item("PH-2", image="/files/ph2.jpg"),
                                item("CB-1", "Cables", image="/files/cb.png")])
        cat = self.cat(shop)
        self.assertEqual([r["code"] for r in cat["rows"]], ["CB-1", "PH-2"])
        self.assertEqual(cat["report"]["disabled"], ["PH-1"])

    def test_an_empty_list_says_so(self):
        out = C.render_html(self.cat(self.shop(prices=[]))["rows"], "D", "L", "2026-10-16")
        self.assertIn("No prices on this list", out)


class Redirects(unittest.TestCase):
    def test_a_scheme_change_is_refused_and_a_plain_http_shop_is_not_accepted(self):
        import urllib.request
        h, req = C._SameHost(), urllib.request.Request("https://shop.example/files/a.png")
        self.assertIsNone(h.redirect_request(req, None, 302, "Found", {}, "http://shop.example/files/a.png"))
        self.assertIsNotNone(h.redirect_request(req, None, 302, "Found", {}, "https://shop.example/files/b.png"))
        with self.assertRaises(SystemExit):
            C.Shop("http://shop.example", "k", "s")
        C.Shop("https://shop.example", "k", "s")

    """A photo request that is redirected: to the same shop it is followed, to another host it is refused and the key stays home."""

    def test_a_redirect_to_another_host_is_refused_and_gets_no_key(self):
        got_key = []

        class Far(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                got_key.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(PNG)

        far = HTTPServer(("127.0.0.1", 0), Far)
        threading.Thread(target=far.serve_forever, daemon=True).start()

        class Near(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/files/out.png":
                    self.send_response(302)
                    self.send_header("Location", f"http://localhost:{far.server_port}/x.png")  # another host name
                elif self.path == "/files/in.png":
                    self.send_response(302)
                    self.send_header("Location", "/files/real.png")
                elif self.path == "/files/real.png":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(PNG)
                    return
                else:
                    self.send_response(404)
                self.end_headers()

        near = HTTPServer(("127.0.0.1", 0), Near)
        threading.Thread(target=near.serve_forever, daemon=True).start()
        try:
            shop = C.Shop(f"http://127.0.0.1:{near.server_port}", "k", "s")
            with self.assertRaises(C.Unreadable):
                shop.file("/files/out.png", 10000)
            self.assertEqual(got_key, [])  # the other host was never asked
            self.assertEqual(shop.file("/files/in.png", 10000), PNG)  # the same host's redirect is followed
            pic, why = C.picture(shop, "/files/gone.png", 10)
            self.assertIsNone(pic)
            self.assertIn("HTTP 404", why)
        finally:
            for s in (far, near):
                s.shutdown()
                s.server_close()


class ShopReads(unittest.TestCase):
    """Shop over HTTP against a local stand-in: the key is sent, order_by goes as text, a long list is paged."""

    def test_paging_auth_and_text_order(self):
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if self.path.startswith("/files/"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"x" * 3000)
                    return
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                start = int(q["limit_start"][0])
                rows = [{"n": i} for i in range(5)][start:start + 2]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": rows}).encode())

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old, C.PAGE = C.PAGE, 2
        try:
            got = C._all(C.Shop(f"http://127.0.0.1:{srv.server_port}", "k", "s"), "Item Price", ["n"], [])
        finally:
            C.PAGE = old
        self.assertEqual([r["n"] for r in got], [0, 1, 2, 3, 4])
        shop = C.Shop(f"http://127.0.0.1:{srv.server_port}", "k", "s")
        self.assertIsNone(shop.file("/files/big.png", 1000))  # over the limit: not read whole, not returned
        self.assertEqual(len(shop.file("/files/big.png", 5000)), 3000)
        self.assertTrue(all(a == "token k:s" for _, a in seen))
        self.assertIn("order_by=name+asc", seen[0][0])  # not %22name+asc%22
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    unittest.main()
