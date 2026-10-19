"""S6 service tests — the service, a stub AI service and the programme's stand-in caller, on this machine, no account:
    python3 -m unittest discover -s samples/s6_ai_till_key/tests -p 'test_service.py' -v
The same checks run on the bench with the till's REAL validator (our test bench's own run, not in the kit); here the validator is a shape
check written for the test, and says so.
"""
import io
import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "..", "tools", "standin_caller")]
import caller  # noqa: E402
import core  # noqa: E402
import providers  # noqa: E402
import service  # noqa: E402
import stub_provider  # noqa: E402

SECRET = "test-point-secret-ABC123"
AI_KEY = "customer-ai-key-XYZ789"
CONTEXT = {"sale_ref": "S-1", "store": "Demo Retail Store 1", "operator": "cashier-SENTINEL@example.com",
           "customer": "Customer-SENTINEL", "lines": [{"item_code": "AIRPODS-3", "qty": 1.0, "luid": "l0"}]}
PAYLOAD = {"app": "pp_ai", "key": "ai_tip", "returns": ["message"], "context": CONTEXT}


def shape_ok(value, allowed):
    """A stand-in for the till's validate_result, for these laptop tests only: (clean, reason)."""
    m = value.get("message") if isinstance(value, dict) and set(value) == {"message"} else None
    ok = (isinstance(m, dict) and set(m) == {"title", "body", "level"} and 0 < len(m["title"]) <= 60
          and 0 < len(m["body"]) <= 280 and m["level"] in ("info", "success", "warning"))
    return (dict(value), "") if ok else (None, "not a valid message")


def leaks(log_text, sentinels):
    return [s for s in sentinels if s in log_text]


class Running:
    """A service (and, if asked, a stub AI service) on ephemeral ports, with its log captured."""
    def __init__(self, provider=None, chat_delay=None):
        self.log = io.StringIO()
        self.ai = None
        if chat_delay is not None:
            self.ai = stub_provider.make_server(0, chat_delay)
            threading.Thread(target=self.ai.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{self.ai.server_address[1]}/v1/chat/completions"
            provider = providers.chat(url, AI_KEY, "stub-model", timeout=8)
        self.srv = service.make_server({"PP_POINT_SECRET": SECRET}, provider or providers.stub, 0, self.log)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/point/ai_tip"

    def ask(self, payload=PAYLOAD, secret=SECRET, timeout=caller.DEADLINE_S):
        return caller.stated_answer(self.url, secret.encode(), payload, "AI tip", shape_ok, timeout)

    def close(self):
        for srv in (self.srv, self.ai):
            if srv:
                srv.shutdown()
                srv.server_close()


class Service(unittest.TestCase):
    def test_good_answer_through_the_stub_provider(self):
        r = Running()
        self.addCleanup(r.close)
        a = r.ask()
        self.assertEqual(a["state"], "result", a)
        self.assertIn("AIRPODS-3", a["message"]["body"])

    def test_good_answer_through_the_chat_provider_and_a_stub_ai_service(self):
        r = Running(chat_delay=0.0)
        self.addCleanup(r.close)
        a = r.ask()
        self.assertEqual(a["state"], "result", a)
        self.assertIn("AIRPODS-3", a["message"]["body"])

    def test_wrong_secret_is_refused(self):
        r = Running()
        self.addCleanup(r.close)
        a = r.ask(secret="not-the-secret")
        self.assertEqual(a["state"], "refused")
        self.assertEqual(a["why"], "http: 401")                 # refused BY THE SIGNATURE CHECK, not by any other failure
        self.assertIn("could not finish", a["detail"])          # a 401 reads as "could not finish" at the till

    def test_old_timestamp_is_refused(self):
        raw = b'{"context": {}}'
        ts = str(int(time.time()) - 3600)
        self.assertFalse(service.verified(SECRET.encode(), {"X-iVendNext-Timestamp": ts,
                         "X-iVendNext-Signature": caller.sign(SECRET.encode(), ts, raw)}, raw))

    def test_provider_failure_gives_no_tip_and_the_stated_refusal(self):
        def broken(prompt):
            raise RuntimeError("upstream said: key " + AI_KEY)
        r = Running(broken)
        self.addCleanup(r.close)
        a = r.ask()
        self.assertEqual(a, {"state": "refused", "detail": caller.COULD_NOT.format("AI tip"), "why": a["why"]})
        self.assertNotIn("message", a)

    def test_slow_provider_gives_the_did_not_answer_in_time_sentence(self):
        r = Running(chat_delay=5.0)             # the AI service takes 5 s; the till's deadline is 3 s
        self.addCleanup(r.close)
        t0 = time.monotonic()
        a = r.ask()
        took = time.monotonic() - t0
        self.assertEqual(a["state"], "refused")
        self.assertEqual(a["detail"], "AI tip did not answer in time. Nothing was added to the sale.")
        self.assertLess(took, 3.6)

    def test_marker_stores_make_the_stub_slow_or_failing(self):
        r = Running(chat_delay=0.0)
        self.addCleanup(r.close)
        slow = r.ask(dict(PAYLOAD, context=dict(CONTEXT, store="PP-SLOW-TEST")))
        self.assertIn("did not answer in time", slow["detail"])
        bad = r.ask(dict(PAYLOAD, context=dict(CONTEXT, store="PP-FAIL-TEST")))
        self.assertEqual(bad["detail"], caller.COULD_NOT.format("AI tip"))

    def test_oversize_request_is_refused_before_it_is_read(self):
        r = Running()
        self.addCleanup(r.close)
        big = dict(PAYLOAD, context=dict(CONTEXT, pad="x" * 70000))
        a = r.ask(big)
        self.assertEqual(a["state"], "refused")
        self.assertTrue(a["why"] == "http: 413" or a["why"].startswith("down:"), a["why"])   # 413, or the server closing on the sender

    def test_the_prompt_the_provider_sees_has_only_what_the_consent_lists(self):
        seen = []
        r = Running(lambda p: (seen.append(p), "A tip.")[1])
        self.addCleanup(r.close)
        r.ask()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], core.build_prompt(CONTEXT))
        for s in ("SENTINEL", "S-1"):
            self.assertNotIn(s, seen[0])


class Redirects(unittest.TestCase):
    def test_the_chat_provider_does_not_follow_a_redirect_with_the_key(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
            do_POST = do_GET

            def log_message(self, *a):
                pass
        target = HTTPServer(("127.0.0.1", 0), Target)

        class Redirector(Target):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(307)
                self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/steal")
                self.end_headers()
        redirector = HTTPServer(("127.0.0.1", 0), Redirector)
        for srv in (target, redirector):
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        p = providers.chat(f"http://127.0.0.1:{redirector.server_address[1]}/v1/chat/completions", AI_KEY, "m", 3)
        with self.assertRaises(Exception) as cm:
            p("prompt")
        self.assertEqual(type(cm.exception).__name__, "HTTPError")
        self.assertEqual(seen, [])                              # the redirect target was never called, key or not
        for srv in (target, redirector):
            srv.shutdown()
            srv.server_close()


class Logs(unittest.TestCase):
    SENTINELS = [SECRET, AI_KEY, "SENTINEL", "AIRPODS-3", "Demo Retail Store 1", "Ask whether", "Authorization", "Signature"]

    def test_no_secret_and_no_prompt_text_in_the_log(self):
        for provider_kwargs in ({}, {"chat_delay": 0.0}, {"provider": lambda p: 1 / 0}):
            r = Running(**provider_kwargs)
            r.ask()                                   # a good call or a failing one
            r.ask(secret="wrong")                     # a refused one
            r.close()
            text = r.log.getvalue()
            self.assertIn("status", text)             # the log is not empty: it holds the request lines
            self.assertEqual(leaks(text, self.SENTINELS), [], text)

    def test_failure_log_names_the_class_only(self):
        def broken(prompt):
            raise RuntimeError("secret " + AI_KEY + " prompt " + prompt[:20])
        r = Running(broken)
        r.ask()
        r.close()
        self.assertIn("RuntimeError", r.log.getvalue())
        self.assertEqual(leaks(r.log.getvalue(), [AI_KEY, "Items on the sale"]), [])

    def test_canary_the_leak_check_can_fail(self):
        self.assertEqual(leaks(f"request x prompt AIRPODS-3 key {AI_KEY}", self.SENTINELS), [AI_KEY, "AIRPODS-3"])
        self.assertEqual(leaks("request x status 200 5 ms", self.SENTINELS), [])


if __name__ == "__main__":
    unittest.main()
