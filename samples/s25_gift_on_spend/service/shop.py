"""S25 — the shop, as your service sees it (copied from samples/s22_customer_loyalty/service/shop.py @ 3546aaf; a defect
here is a defect there — report it on the Partner feedback forms): the record API with the one integration user's key (standard library only).

Token auth, JSON, no redirect followed (a key never travels to another host), the server's own sentence on a refusal,
never its traceback (the shape of tools/feed_client ``Api``).

``Duplicate`` is the shop refusing a second record with the same name (HTTP 409): every Card record is NAMED
by its unique key, so the shop itself refuses a second row for the same event, and the service treats that refusal as
"already done". Your own note of handled events is only a cache in front of it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


# Names this service on every call it makes to the shop's record API: some network edges refuse the default signature
# of a programming language's HTTP library (the starter note's first rule, recipes/wallet.md). Put your own app's name
# here. The event feed's calls go through tools/feed_client, which names itself the same way.
USER_AGENT = "s25-gift-card-on-spend/1"


class ShopError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status} {message}")
        self.status, self.message = status, message


class Duplicate(ShopError):
    """409: a record with this name exists already."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _server_message(raw: bytes) -> str:
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        return raw[:200].decode(errors="replace")
    for k in ("_server_messages", "message", "exception", "exc_type"):
        if d.get(k):
            v = d[k]
            if k == "_server_messages":
                try:
                    v = "; ".join(json.loads(m).get("message", m) for m in json.loads(v))
                except (ValueError, AttributeError):
                    pass
            return str(v)[:300]
    return ""


class Shop:
    def __init__(self, base: str, key: str, secret: str, timeout: float = 20):
        self.base, self.timeout = base.rstrip("/"), timeout
        self._auth = f"token {key}:{secret}"
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = None if body is None else json.dumps(body, default=str).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": self._auth, "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": USER_AGENT})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            msg = _server_message(e.read())
            raise (Duplicate if e.code == 409 else ShopError)(e.code, msg) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ShopError(0, f"unreachable: {e}") from None

    @staticmethod
    def _q(dt: str, name: str | None = None) -> str:
        p = "/api/resource/" + urllib.parse.quote(dt)
        return p if name is None else f"{p}/{urllib.parse.quote(name, safe='')}"

    def get(self, dt: str, name: str) -> dict | None:
        try:
            return self._call("GET", self._q(dt, name)).get("data")
        except ShopError as e:
            if e.status == 404:
                return None
            raise

    def list(self, dt: str, filters=None, fields=("name",), order_by: str = "creation asc", limit: int = 0) -> list[dict]:
        return self._call("GET", self._q(dt), {
            "filters": json.dumps(filters or []), "fields": json.dumps(list(fields)), "order_by": order_by,
            "limit_page_length": limit}).get("data", [])

    def insert(self, doc: dict) -> str:
        """Create; returns the name. ``Duplicate`` when the name is taken (the unique key)."""
        return self._call("POST", self._q(doc["doctype"]), body=doc)["data"]["name"]

    def update(self, dt: str, name: str, fields: dict) -> dict:
        return self._call("PUT", self._q(dt, name), body=fields).get("data", {})

    def delete(self, dt: str, name: str):
        self._call("DELETE", self._q(dt, name))

    def method(self, dotted: str, body: dict | None = None):
        return self._call("POST", f"/api/method/{dotted}", body=body or {}).get("message")
