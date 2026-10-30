"""S59's live service (``live/live.py`` and ``live/sitesocket.py``) against a stand-in site socket (``fakesite.py``) and the
stand-in shop (``fakeshop.py``): a screen's line hears its own store's notices and no other's, only a valid link opens a
line, the socket signs in as the app's own user and comes back after a drop, a site that names itself apart from its
address is still reached, no key reaches a log line, and the container's image holds what it imports.

    python3 -m unittest discover -s samples/s59_kitchen_screen/tests -p 'test_*.py'
"""

import contextlib
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [HERE, os.path.join(SAMPLE, "live"), os.path.join(SAMPLE, "service"), SAMPLE]
import app  # noqa: E402
import fakeshop as F  # noqa: E402
import fakesite  # noqa: E402
import ksc  # noqa: E402
import live  # noqa: E402
import shops  # noqa: E402
import sitesocket  # noqa: E402

APP = "pp_ksc"
USER = "user:pp_ksc@integration.invalid"


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Out(io.StringIO):
    """Every line printed while a test runs, from every thread."""


def link_for(site, name, number=1):
    token = ksc.link_of(F.PAGE, site, name, number, F.SECRET.encode()).split("&t=", 1)[1]
    return {"s": site, "t": __import__("urllib.parse").parse.unquote(token)}


class LiveTest(unittest.TestCase):
    def setUp(self):
        self._backoff = sitesocket.BACKOFF
        sitesocket.BACKOFF = (0.05, 0.1, 0.2)
        self.out = Out()
        for r in (contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out)):   # tracebacks too
            r.__enter__()
            self.addCleanup(r.__exit__, None, None, None)
        self.addCleanup(setattr, sitesocket, "BACKOFF", self._backoff)

    def start(self, name=None, key=fakesite.KEY, screens=None, site_key=None, **site):
        self.site = fakesite.FakeSite(name=name, key=key, **site)
        self.addCleanup(self.site.stop)
        grill = F.screen("KSC-SCREEN-00001", number=1)
        grill["made_for"] = ksc.made_for(grill)
        other = F.screen("KSC-SCREEN-00009", number=1, store=F.OTHER)
        other["made_for"] = ksc.made_for(other)
        self.shop = F.FakeTenant(screens=screens or [grill, other])
        self.shop.settings[F.CO]["stores"].append(dict(F.settings()["stores"][0], store=F.OTHER))
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.store = store = shops.FileStore(os.path.join(tmp, "shops.json"), local=True)
        store.put(self.site.site, {"site": self.site.site, "url": self.site.url, "previous": {},
                                   "secrets": {f"{APP}:sub:link": F.SECRET, USER: site_key or fakesite.KEY,
                                               "user:Administrator": "admin:never"}})
        svc = app.Service({"IVN_LIBRARY_APP": APP, "KSC_PREFIX": "PP KSC", "KSC_PAGE_URL": F.PAGE}, store=store,
                          tenants=lambda url, key: self.shop)
        self.hub = live.Hub(svc)
        self.http = live.Server(("127.0.0.1", 0), live.handler(self.hub, F.PAGE, heartbeat_s=0.3, life_s=4))
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.addCleanup(lambda: [e["stop"].set() for e in list(self.hub.sockets.values())])

    def open_line(self, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_address[1], timeout=5)
        self.addCleanup(conn.close)
        conn.request("POST", "/ksc/live", body=json.dumps(body), headers={"Content-Type": "text/plain;charset=UTF-8"})
        return conn.getresponse()

    def events(self, resp, until, seconds=4.0):
        """The events read from a line until one matches ``until`` (name, data) or ``seconds`` pass."""
        got, end = [], time.monotonic() + seconds
        resp.fp.raw._sock.settimeout(0.5)
        name = data = None
        while time.monotonic() < end:
            try:
                ln = resp.fp.readline()
            except OSError:
                continue
            if not ln:
                break
            ln = ln.decode().rstrip("\n")
            if ln.startswith("event: "):
                name = ln[7:]
            elif ln.startswith("data: "):
                data = json.loads(ln[6:])
            elif ln == "" and name:
                got.append((name, data))
                if until and until(name, data):
                    return got
                name = data = None
        return got

    def up(self, resp):
        return self.events(resp, lambda n, d: n == "state" and d == {"live": True})

    # ── a line ──
    def test_v1_a_screens_line_hears_its_own_stores_notice_and_not_another_stores(self):
        self.start()
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "text/event-stream"))
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), F.PAGE)    # the screens' page alone may read it
        first = self.up(r)
        self.assertEqual(first[0], ("state", {"live": False}))                # not yet up: the page keeps its 3 s
        self.assertEqual(first[-1], ("state", {"live": True}))
        self.events(r, lambda n, d: n == "read", 1)                            # the catch-up read after the sign-in
        self.site.push(F.OTHER)
        self.assertEqual([e for e in self.events(r, None, 1.0) if e[0] == "read"], [])   # another store: nothing
        t0 = time.monotonic()
        self.site.push(F.STORE)
        got = self.events(r, lambda n, d: n == "read", 3)
        self.assertEqual(got[-1], ("read", {}))
        self.assertLess(time.monotonic() - t0, 1.0)                            # within a second

    def test_v2_a_forged_or_replaced_link_opens_no_line_and_no_socket(self):
        self.start()
        bad = link_for(self.site.site, "KSC-SCREEN-00001")
        bad["t"] = bad["t"][:-3] + ("AAA" if not bad["t"].endswith("AAA") else "BBB")
        r = self.open_line(bad)
        self.assertEqual((r.status, json.loads(r.read())), (404, {"state": "unknown"}))
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001", number=2))     # a number the record has not reached
        self.assertEqual((r.status, json.loads(r.read())), (404, {"state": "unknown"}))
        r = self.open_line(link_for("elsewhere.example.com", "KSC-SCREEN-00001"))      # a retailer the service does not know
        self.assertEqual((r.status, json.loads(r.read())), (404, {"state": "unknown"}))
        self.assertEqual((self.hub.sockets, self.site.hs), ({}, {}))                    # no socket was opened

    def test_v3_the_socket_signs_in_as_the_apps_own_user_with_the_sites_origin_and_no_sid(self):
        self.start()
        self.up(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")))
        hs = list(self.site.hs.values())[-1]
        self.assertEqual(hs["Authorization"], f"token {fakesite.KEY}")     # the app's user, never Administrator
        self.assertEqual(hs["Origin"], self.site.url)
        self.assertNotIn("sid=", hs["Cookie"])
        self.assertTrue(self.site.signed_in())

    def test_v4_a_dropped_socket_says_so_then_comes_back_and_every_screen_reads(self):
        self.start()
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.up(r)
        self.site.drop()
        got = self.events(r, lambda n, d: n == "state" and d == {"live": True}, 6)
        self.assertIn(("state", {"live": False}), got)                         # the page goes back to its 3 s at once
        self.assertEqual(got[-1], ("state", {"live": True}))
        self.assertEqual(self.events(r, lambda n, d: n == "read", 2)[-1], ("read", {}))   # what it missed: read now
        self.assertIn('"socket": "signed in"', self.out.getvalue())

    def test_v5_a_site_named_apart_from_its_address_is_reached_by_its_own_name(self):
        self.start(name="shop-internal.example.com")
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual(self.up(r)[-1], ("state", {"live": True}))
        self.assertEqual((self.hub.names, self.site.pages), ({self.site.site: "shop-internal.example.com"}, 1))
        self.site.push(F.STORE)
        self.assertEqual(self.events(r, lambda n, d: n == "read", 3)[-1], ("read", {}))

    def test_v6_no_key_or_secret_reaches_a_log_line_and_a_wrong_key_is_refused(self):
        self.start(site_key="k3y-app-user:wrong-secret-99")
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.events(r, None, 1.5)
        self.assertFalse(self.site.signed_in())
        text = self.out.getvalue()
        self.assertIn('"socket": "refused: Unauthorized: token -"', text)     # the echoed key taken out
        for secret in ("k3y-app-user", "wrong-secret-99", "s3cret-app-user", F.SECRET, "admin:never"):
            self.assertNotIn(secret, text)

    def test_v7_a_line_ends_with_again_and_the_socket_closes_after_the_last_line(self):
        self.start()
        clock = Clock()
        self.hub.clock = clock
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual(self.events(r, lambda n, d: n == "again", 6)[-1], ("again", {}))
        r.close()
        deadline = time.monotonic() + 3
        while self.hub.lines and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.hub.lines, {})
        self.hub.sweep()
        self.assertIn(self.site.site, self.hub.sockets)              # kept a minute for a page that opens it again
        clock.t += live.LINGER_S
        self.hub.sweep()
        self.assertEqual(self.hub.sockets, {})

    def test_v8_too_many_lines_are_refused_busy_and_the_page_falls_back(self):
        self.start()
        old = live.SITE_STREAMS_MAX
        live.SITE_STREAMS_MAX = 1
        self.addCleanup(setattr, live, "SITE_STREAMS_MAX", old)
        self.up(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")))
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual((r.status, json.loads(r.read())), (503, {"state": "busy"}))


    def test_v9_a_key_replaced_by_connect_again_ends_the_socket_signed_in_with_the_old_one(self):
        self.start()
        self.up(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")))
        old = self.hub.sockets[self.site.site]
        new_key = "k3y-app-user:s3cret-after-connect-again"
        rec = self.store.get(self.site.site)
        rec["secrets"][USER] = new_key
        self.store.put(self.site.site, rec)
        self.site.key = new_key                                   # the site now takes only the new key
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertTrue(old["stop"].is_set())
        self.assertIsNot(self.hub.sockets[self.site.site], old)
        self.assertEqual(self.up(r)[-1], ("state", {"live": True}))
        self.assertEqual(list(self.site.hs.values())[-1]["Authorization"], f"token {new_key}")

    def test_v12_a_key_replaced_while_the_retailer_is_at_its_cap_still_tells_its_screens_and_comes_back(self):
        self.start()
        old_max = live.SITE_STREAMS_MAX
        live.SITE_STREAMS_MAX = 1
        self.addCleanup(setattr, live, "SITE_STREAMS_MAX", old_max)
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.up(r)
        new_key = "k3y-app-user:s3cret-after-connect-again"
        rec = self.store.get(self.site.site)
        rec["secrets"][USER] = new_key
        self.store.put(self.site.site, rec)
        self.site.key = new_key
        busy = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual((busy.status, json.loads(busy.read())), (503, {"state": "busy"}))
        got = self.events(r, lambda n, d: n == "state" and d == {"live": True}, 6)
        self.assertIn(("state", {"live": False}), got)                         # down at once, then back
        self.assertEqual(got[-1], ("state", {"live": True}))
        self.assertEqual(list(self.site.hs.values())[-1]["Authorization"], f"token {new_key}")

    def test_v13_a_socket_whose_lines_are_gone_is_swept_even_when_a_busy_refusal_cleared_its_mark(self):
        self.start()
        clock = Clock()
        self.hub.clock = clock
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.up(r)
        r.close()
        deadline = time.monotonic() + 3
        while self.hub.lines and time.monotonic() < deadline:
            time.sleep(0.05)
        old_max = live.SITE_STREAMS_MAX
        live.SITE_STREAMS_MAX = 0                                   # the copy is full: a screen of this retailer is refused
        self.addCleanup(setattr, live, "SITE_STREAMS_MAX", old_max)
        busy = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual(busy.status, 503)
        self.assertIsNotNone(self.hub.sockets[self.site.site]["idle_since"])   # the refusal left the linger mark alone
        self.hub.sockets[self.site.site]["idle_since"] = None      # and a socket with no mark at all is still swept
        self.hub.sweep()
        clock.t += live.LINGER_S
        self.hub.sweep()
        self.assertEqual(self.hub.sockets, {})

    def test_v14_an_edges_small_page_at_app_is_not_parked_as_no_name(self):
        self.start(name="shop-internal.example.com")
        self.site.edge_page = "<html>down for maintenance</html>"
        self.events(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")), None, 1.5)
        self.assertEqual(self.hub.name_tried, {})                          # not parked: read again at the next refusal
        self.site.edge_page = None                                         # maintenance over
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual(self.up(r)[-1], ("state", {"live": True}))

    def test_v10_a_site_whose_desk_page_names_no_site_is_not_read_again_at_once(self):
        self.start(name="shop-internal.example.com", named=False)
        self.events(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")), None, 2.5)
        self.assertEqual((self.site.pages, self.hub.names), (1, {}))     # several refusals, one read of the page
        self.assertGreaterEqual(self.out.getvalue().count("Invalid namespace"), 2)
        clock = Clock(self.hub.clock())
        self.hub.clock = clock
        self.hub.name_tried = {k: clock() for k in self.hub.name_tried}
        clock.t += 1800                                                  # half an hour on (the README's bound): read again
        self.events(self.open_line(link_for(self.site.site, "KSC-SCREEN-00001")), None, 2.5)
        self.assertEqual(self.site.pages, 2)

    def test_v11_a_desk_page_that_failed_to_answer_is_read_again_at_the_next_refusal(self):
        self.start(name="shop-internal.example.com", page_fails=1)        # one 502, then the page names the site
        r = self.open_line(link_for(self.site.site, "KSC-SCREEN-00001"))
        self.assertEqual(self.up(r)[-1], ("state", {"live": True}))
        self.assertEqual((self.site.pages, self.hub.names[self.site.site]), (2, "shop-internal.example.com"))


class ServerTest(unittest.TestCase):
    def test_c1_connections_past_the_cap_are_closed_before_they_are_read(self):
        import socket
        srv = live.Server(("127.0.0.1", 0), live.handler(None, F.PAGE), most=2)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        held = [socket.create_connection(srv.server_address, timeout=3) for _ in range(2)]   # two slow callers
        for c in held:
            self.addCleanup(c.close)
        time.sleep(0.3)
        third = socket.create_connection(srv.server_address, timeout=3)
        self.addCleanup(third.close)
        self.assertEqual(third.recv(1), b"")                    # closed at once, never read
        held[0].close()
        time.sleep(0.5)                                          # its slot comes back when its handler ends (10 s read
        # timeout) or the caller goes: a fresh caller is served once a slot is free
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            c = socket.create_connection(srv.server_address, timeout=3)
            c.sendall(b"GET /health HTTP/1.0\r\n\r\n")
            got = c.recv(64)
            c.close()
            if got:
                break
            time.sleep(0.5)
        self.assertTrue(got.startswith(b"HTTP/1.0 200"))


class SocketTest(unittest.TestCase):
    def test_k1_a_notice_of_another_event_or_shape_is_not_passed_on(self):
        heard = []
        s = sitesocket.Session("https://shop.example.com", fakesite.KEY, lambda st, sn: heard.append((st, sn)))
        s.notice('42/shop.example.com,["mpos_station_ticket",{"store":"A","station":"Grill"}]')
        s.notice('42/shop.example.com,["list_update",{"store":"A"}]')
        s.notice('42/other.example.com,["mpos_station_ticket",{"store":"B"}]')
        s.notice('42/shop.example.com,["mpos_station_ticket",{"store":7}]')
        s.notice('42/shop.example.com,5["mpos_station_ticket",{"store":"C"}]')
        self.assertEqual(heard, [("A", "Grill"), ("C", "")])

    def test_k2_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        site = fakesite.FakeSite(redirect=True)
        self.addCleanup(site.stop)
        s = sitesocket.Session(site.url, fakesite.KEY, lambda *a: None)
        with self.assertRaises(sitesocket.Lost) as e:
            s.handshake()
        self.assertTrue(e.exception.refused)
        self.assertEqual(len(site.headers), 1)                 # one request, to the site itself

    def test_k3_pings_are_answered_and_the_edges_cookie_is_sent_back(self):
        site = fakesite.FakeSite(ping_ms=200)
        self.addCleanup(site.stop)
        s = sitesocket.Session(site.url, fakesite.KEY, lambda *a: None)
        s.handshake()
        s.sign_in()
        for _ in range(3):
            s.poll()
        s.close()
        self.assertGreaterEqual(site.pongs, 2)
        self.assertEqual(len(set(site.poll_ts)), len(site.poll_ts))     # each poll's address is new: never a cached answer
        self.assertTrue(all(site.poll_ts))
        self.assertIn("edge=sticky-1", site.headers[-1]["Cookie"])

    def test_k5_an_answer_with_no_packet_ends_the_session_never_asks_again_at_once(self):
        for body in ("", "200 OK", "404 page not found", "2xx maintenance", "<html>maintenance</html>"):
            site = fakesite.FakeSite(poll_body=body)   # an edge answering 200 with an empty body or its own page
            self.addCleanup(site.stop)
            s = sitesocket.Session(site.url, fakesite.KEY, lambda *a: None)
            s.handshake()
            with self.assertRaises(sitesocket.Lost, msg=body) as e:
                s.sign_in()
            self.assertEqual((e.exception.why, site.polls), ("an answer with no packet", 1), body)

    def test_k4_the_pause_grows_while_sessions_fail_and_stops_on_stop(self):
        stop, pauses, said = threading.Event(), [], []

        def make():
            if len(pauses) >= 5:
                stop.set()
            raise sitesocket.Lost("GET ConnectionRefusedError")

        sitesocket.hold(make, stop, said.append, sleep=pauses.append, rand=lambda: 0.5)
        self.assertEqual(pauses, [1, 2, 4, 8, 15, 30][:len(pauses)])
        self.assertTrue(all(s == "lost: GET ConnectionRefusedError" for s in said))


class ImageTest(unittest.TestCase):
    def test_i1_the_container_holds_what_it_imports_and_passes_the_hosting_checks(self):
        """The image is built from the Dockerfile's COPY lines alone: copy exactly those, then start it with no settings.
        It must stop on its own words about the settings, never on a missing module (HOSP-K1b's fit.js lesson)."""
        docker = open(os.path.join(SAMPLE, "live", "Dockerfile")).read()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for line in re.findall(r"^COPY (.+)$", docker, re.M):
            *srcs, dest = line.split()
            for src in srcs:
                full = os.path.join(KIT, src.rstrip("/"))
                target = os.path.join(tmp, dest.lstrip("/").replace("app/", "", 1))
                if os.path.isdir(full):
                    shutil.copytree(full, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    os.makedirs(target if dest.endswith("/") else os.path.dirname(target), exist_ok=True)
                    shutil.copy(full, os.path.join(target, os.path.basename(src)) if dest.endswith("/") else target)
        cmd = json.loads(re.search(r"^CMD (.+)$", docker, re.M).group(1))
        p = subprocess.run([sys.executable, "-I", *cmd[1:]], cwd=tmp, capture_output=True, text=True, timeout=60,
                           env={"PATH": os.environ.get("PATH", "")})
        self.assertIn("set IVN_LIBRARY_APP", p.stderr)
        self.assertNotIn("ModuleNotFoundError", p.stderr)
        here = os.path.relpath(os.path.join(SAMPLE, "live"), KIT)
        tools = [["tools/app_template/validate_app.py", here]]
        if os.path.exists(os.path.join(KIT, "LICENSE")):     # the hosting's own check wants the repository's licence
            tools.append(["tools/deploy_app/deploy_app.py", here, "--image",
                          "registry.example/partner-apps/kitchen-screen-live:1.1.0", "--plan", "starter", "--partner", "acme"])
        for tool in tools:
            r = subprocess.run([sys.executable, *tool], cwd=KIT, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_i2_the_live_service_and_the_service_share_one_version(self):
        a = json.load(open(os.path.join(SAMPLE, "app.json")))
        b = json.load(open(os.path.join(SAMPLE, "live", "app.json")))
        self.assertEqual(a["version"], b["version"])
        self.assertNotIn("runs", b)                             # a container: no handler, no package
        self.assertFalse(b.get("shops"))                        # it reads the service's table; it has none of its own


if __name__ == "__main__":
    unittest.main()
