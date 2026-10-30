"""A stand-in for a retailer's own live channel as S59's live service reaches it: the site's socket over the long-polling
transport (engine.io 4, socket.io 5), on 127.0.0.1. It signs a connection in to the namespace ``/<its name>`` only with
the app user's key, the site's own origin and a cookie that holds no ``sid``, as the site's socket does; it pings, it
pushes ``mpos_station_ticket`` notices to every signed-in connection, it can drop every connection, and its Desk page
(``/app``) names the site to a request with the key. It records each request's headers for the tests."""

import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "k3y-app-user:s3cret-app-user"
SEP = "\x1e"


class FakeSite:
    def __init__(self, name=None, key=KEY, ping_ms=400, redirect=False, poll_body=None, named=True, page_fails=0):
        self.key, self.ping_ms, self.redirect = key, ping_ms, redirect
        self.poll_body, self.named, self.polls = poll_body, named, 0    # poll_body: an edge answering 200 with no packet
        self.page_fails = page_fails                                    # the Desk page answers 502 this many times first
        self.poll_ts = []                                               # each long poll's t= (a fresh one each time)
        self.edge_page = None                                           # /app answers this small page (an edge's)
        self.refuse_ns = False
        self.lock = threading.Condition()
        self.queues, self.signed, self.headers, self.pongs, self.closed, self.pages = {}, set(), [], 0, [], 0
        site = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, code, text, ctype="text/plain; charset=UTF-8", extra=None):
                data = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                site.headers.append(dict(self.headers))
                url = urllib.parse.urlsplit(self.path)
                if url.path == "/app":
                    site.pages += 1
                    if site.edge_page is not None:
                        return self._send(200, site.edge_page, "text/html")
                    if site.page_fails > 0:
                        site.page_fails -= 1
                        return self._send(502, "bad gateway")
                    if self.headers.get("Authorization") != f"token {site.key}":
                        return self._send(403, "no")
                    return self._send(200, '<script>frappe.boot = {"sitename": "%s"}</script>' % site.name
                                      if site.named else "<html>a Desk page with no boot data" + " " * 70000 + "</html>",
                                      "text/html")
                q = dict(urllib.parse.parse_qsl(url.query))
                if site.redirect:
                    return self._send(302, "", extra={"Location": "http://127.0.0.1:9/elsewhere"})
                if "sid" not in q:                    # the handshake: its headers are the connection's
                    sid = uuid.uuid4().hex
                    with site.lock:
                        site.queues[sid] = []
                        site.hs[sid] = dict(self.headers)
                    return self._send(200, "0" + json.dumps({"sid": sid, "upgrades": [], "pingInterval": site.ping_ms,
                                                             "pingTimeout": site.ping_ms}),
                                      extra={"Set-Cookie": "edge=sticky-1; Path=/"})
                sid = q["sid"]
                site.polls += 1
                site.poll_ts.append(q.get("t", ""))
                if site.poll_body is not None:
                    return self._send(200, site.poll_body)
                with site.lock:
                    if sid not in site.queues:
                        return self._send(400, '{"code":1,"message":"Session ID unknown"}')
                    if not site.queues[sid]:
                        site.lock.wait(site.ping_ms / 1000)
                    if sid not in site.queues:
                        return self._send(400, '{"code":1,"message":"Session ID unknown"}')
                    out = site.queues[sid] or ["2"]
                    site.queues[sid] = []
                self._send(200, SEP.join(out))

            def do_POST(self):
                site.headers.append(dict(self.headers))
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                sid = q.get("sid", "")
                with site.lock:
                    if sid not in site.queues:
                        return self._send(400, '{"code":1,"message":"Session ID unknown"}')
                    for packet in body.split(SEP):
                        site.packet(sid, packet)
                    site.lock.notify_all()
                self._send(200, "ok")

            def log_message(self, *a):
                pass

        self.hs = {}
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.site = f"127.0.0.1:{self.port}"
        self.url = f"http://{self.site}"
        self.name = name or "127.0.0.1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def packet(self, sid, packet):          # under the lock
        ns = "/" + self.name
        if packet == "3":
            self.pongs += 1
        elif packet == "1":
            self.queues.pop(sid, None)
            self.signed.discard(sid)
        elif packet.startswith("41"):
            self.closed.append(sid)
            self.signed.discard(sid)
        elif packet.startswith("40"):
            want = packet[2:].split(",", 1)[0]
            h = self.hs[sid]
            cookie = h.get("Cookie") or ""
            host = (h.get("Host") or "").split(":")[0]
            origin = urllib.parse.urlsplit(h.get("Origin") or "").hostname or ""
            if want != ns or self.refuse_ns:              # refuse_ns: refused though the name is right (a node without the site)
                why = "Invalid namespace"
            elif host != origin:
                why = "Invalid origin"
            elif not cookie:
                why = "No cookie transmitted."
            elif any(c.strip().split("=", 1)[0] == "sid" for c in cookie.split(";")):
                why = "a session cookie"
            elif h.get("Authorization") != f"token {self.key}":
                why = "Unauthorized: " + (h.get("Authorization") or "")      # echoes what it refused, as a site may
            else:
                why = ""
            if why:
                self.queues[sid].append(f"44{want}," + json.dumps({"message": why}))
            else:
                self.signed.add(sid)
                self.queues[sid].append(f"40{ns}," + json.dumps({"sid": uuid.uuid4().hex}))

    def push(self, store, station="Grill", event="mpos_station_ticket"):
        with self.lock:
            for sid in self.signed:
                self.queues[sid].append(f"42/{self.name}," + json.dumps([event, {"store": store, "station": station}]))
            self.lock.notify_all()

    def drop(self):
        """Every connection is lost (the site's socket server restarted)."""
        with self.lock:
            self.queues.clear()
            self.signed.clear()
            self.lock.notify_all()

    def signed_in(self):
        with self.lock:
            return len(self.signed)

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
