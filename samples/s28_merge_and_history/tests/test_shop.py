"""S28 — what the real ``Shop`` sends over the record API: the sales reads ask for this customer, submitted, no roll-up,
at most x; the merge writes one new count and comments, and never edits or deletes a count.

    python3 -m unittest discover -s samples/s28_merge_and_history/tests -p 'test_*.py'
"""

import io
import json
import unittest
import urllib.parse
from unittest import mock

from fakes import app, history, merge


class Recorder:
    def __init__(self, answer=None):
        self.calls, self.answer = [], answer or {"data": []}

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        q = {k: v[0] if k == "order_by" else json.loads(v[0]) for k, v in urllib.parse.parse_qs(url.query).items()}
        self.calls.append((req.get_method(), urllib.parse.unquote(url.path), q, json.loads(req.data) if req.data else None))
        return io.BytesIO(json.dumps(self.answer).encode())


def shop_with(rec):
    s = app.Shop("https://shop.example", "k", "s")
    return s, mock.patch.object(app.urllib.request, "urlopen", rec)


class Reads(unittest.TestCase):
    def test_the_sales_invoice_read_skips_roll_ups_and_asks_for_x(self):
        rec = Recorder()
        s, patch = shop_with(rec)
        with patch:
            s.sales(history.SI, "Ann", 7)
            s.sales(history.POS, "Ann", 7)
        (_m, path, q, _b), (_m2, path2, q2, _b2) = rec.calls
        self.assertEqual(path, "/api/resource/Sales Invoice")
        self.assertEqual(q["filters"], [["customer", "=", "Ann"], ["docstatus", "=", 1], ["is_consolidated", "=", 0]])
        self.assertEqual((q["limit_page_length"], q2["limit_page_length"]), (7, 7))
        self.assertEqual(q2["filters"], [["customer", "=", "Ann"], ["docstatus", "=", 1]])

    def test_the_newest_are_asked_for_in_plain_text(self):
        rec = Recorder()
        s, patch = shop_with(rec)
        with patch:
            s.sales(history.POS, "Ann", 3)
        self.assertEqual(rec.calls[0][2]["order_by"], "posting_date desc, posting_time desc")

    def test_the_merge_writes_only_a_new_count_and_comments(self):
        rec = Recorder({"data": {"name": "N"}})
        s, patch = shop_with(rec)
        with patch:
            s.create_count({"doctype": merge.COUNT, "items": []})
            s.add_comment("A", "merged into N")
        self.assertEqual([(m, p) for m, p, _q, _b in rec.calls],
                         [("POST", "/api/resource/Stock Reconciliation"), ("POST", "/api/resource/Comment")])
        self.assertEqual(rec.calls[1][3], {"comment_type": "Comment", "reference_doctype": merge.COUNT,
                                           "reference_name": "A", "content": "merged into N"})
        src = open(app.__file__).read()
        self.assertNotIn('"PUT"', src)
        self.assertNotIn('"DELETE"', src)


if __name__ == "__main__":
    unittest.main()
