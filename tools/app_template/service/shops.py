"""The shops an app serves, and the handshake that adds them: one app, many shops, each with its own secrets.

After a shop installs the app from the App library, the shop's site sends ONE call (guide chapter 14b):

    POST /ivendnext/connect      X-iVendNext-Site: shop-a.ivendnext.com
    {"key": "IVN1-…", "site": "shop-a.ivendnext.com", "secrets": {"<the record's name>": "<its secret>", …}}

`check_key` checks the library key: our signature, by one of the two pinned public keys (L1 signs paid keys, F1 free
keys only), for THIS app (`IVN_LIBRARY_APP`, its catalogue id) and THIS site (the key's host is the site the call
names). Nothing else: no end date, no withdrawn list, no rate limit. Then the shop is
stored with its secrets, and the app calls the shop back at https://<site> (http in local mode, below; its key address serves it), never at an
address the call chooses. A second connect from the same site replaces them and keeps the old ones as the previous
set, accepted while the shop's site moves over (the template's rotation overlap). `POST /ivendnext/disconnect` with the
same key forgets the shop. On every other call the site names itself (`X-iVendNext-Site`), and the call is checked with
THAT shop's own secret; a site the app does not know gets 401.

⚠ The bound we keep on purpose: the key is a bearer credential. Whoever holds a shop's key can connect as that shop
and replace its secrets; the shop's next install of the app connects it again.

Two stores behind one small interface (`get`, `put`, `delete`, `sites`, and `claim`: a call's short hold on a name,
which every copy of the app sees, so two copies never do the same work at once): a JSON file (`IVN_SHOPS_FILE`: tests, your
laptop, your own server) and, on CitiXsys hosting, the app's own encrypted table (`IVN_SHOPS_TABLE`, `dynamo.py`).

LOCAL MODE (`IVN_LOCAL=1`, with the file store only): a shop on this machine — `localhost`, `<name>.localhost`,
`127.0.0.1` or `[::1]`, with or without a port, as a local bench serves it — may connect, and the app calls it back over plain
http. `IVN_LOCAL_LIBRARY_KEYS` names a JSON file of public keys you made (`local_key.py`) that may sign a key for such a
shop, and for no other. Every other site keeps https and our two pinned keys; the table refuses local mode.
"""

from __future__ import annotations

import base64
import binascii
import datetime
import json
import os
import re
import threading

import ed25519

# Our library's public keys (32 bytes, base64) and what each may sign: the POS app pins the same two
# (iVendNext_PWA `ivendnext_mpos/business_logic/app_library.py` LIBRARY_KEYS; a key added there is added here).
LIBRARY_KEYS = {
    "L1": ("I2J5gk09ohs/5a9U4RFg7DF6Umd2G2MaBLCboRsTbcw=", frozenset({"paid"})),
    "F1": ("rFzo2hELUjQePkGpIMBIV938vkgwRrAkT3fH9SQd38o=", frozenset({"free"})),
}
CONNECT, DISCONNECT, SITE_HEADER = "/ivendnext/connect", "/ivendnext/disconnect", "X-iVendNext-Site"
PAYLOAD_MAX, SECRETS_MAX, NAME_MAX, VALUE_MAX = 1024, 100, 200, 2048
CLAIM_MARK = "|"       # in a claim's name (``claim``), never in a site's: a claim is never taken for a shop
SITE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
LOCAL_SITE = re.compile(r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*localhost|127\.0\.0\.1|\[::1\])(:[0-9]{1,5})?")
_B64U = re.compile(r"[A-Za-z0-9_-]+")


class Refused(Exception):
    """A connect the app will not take; ``code`` goes back to the site."""

    def __init__(self, code: str, status: int = 403):
        super().__init__(code)
        self.code, self.status = code, status


def _b64u(text: str) -> bytes | None:
    if not _B64U.fullmatch(text or ""):
        return None
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None


def site_of(value) -> str | None:
    """A site's key address: lower case, no path, no port (but a shop on this machine's). None for anything else.
    A name on this machine only ever has a record when local mode connected it (``connect``)."""
    s = (value or "").strip().lower() if isinstance(value, str) else ""
    return s if len(s) <= 253 and (SITE.fullmatch(s) or LOCAL_SITE.fullmatch(s)) else None


def is_local(site: str) -> bool:
    """A shop on this machine: called back over plain http, in local mode only."""
    return LOCAL_SITE.fullmatch(site or "") is not None


def local_mode(env) -> bool:
    return (env.get("IVN_LOCAL") or "").strip() == "1"


def local_keys(path: str) -> dict:
    """The public keys in ``IVN_LOCAL_LIBRARY_KEYS``: {"<kid>": ["<base64 public key>", ["paid", "free"]]}."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        keys = {kid: (pub, frozenset(kinds)) for kid, (pub, kinds) in raw.items()}
    except (OSError, ValueError, TypeError, AttributeError) as e:
        raise SystemExit(f"IVN_LOCAL_LIBRARY_KEYS: cannot read {path}: {e}")
    try:
        good = all(len(base64.b64decode(pub, validate=True)) == 32 and kinds <= {"paid", "free"}
                   for pub, kinds in keys.values())
    except (binascii.Error, ValueError, TypeError):
        good = False
    if not good:
        raise SystemExit(f"IVN_LOCAL_LIBRARY_KEYS: {path} is not a file local_key.py made")
    if set(keys) & set(LIBRARY_KEYS):
        raise SystemExit(f"IVN_LOCAL_LIBRARY_KEYS: {path} names a pinned key ({', '.join(sorted(set(keys) & set(LIBRARY_KEYS)))})")
    return keys


def check_key(line, app: str, site: str, keys: dict | None = None) -> dict:
    """The key's payload when it is ours, for ``app`` and ``site``; else ``Refused``. Checks in the site's order:
    the form · a pinned ``kid`` whose key may sign this kind, and its signature · the app · the site."""
    text = "".join(str(line or "").split())                 # a mail client's spaces and line breaks
    parts = text[5:].split(".") if text.startswith("IVN1-") else []
    pb, sig = (_b64u(parts[0]), _b64u(parts[1])) if len(parts) == 2 else (None, None)
    try:
        payload = json.loads(pb) if pb and len(pb) <= PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or payload.get("typ") != "applib-key" or payload.get("v") != 1 \
            or payload.get("kind") not in ("free", "paid") or not all(
                isinstance(payload.get(f), str) for f in ("kid", "id", "app", "host")):
        raise Refused("key_form")
    public, may_sign = (keys or LIBRARY_KEYS).get(payload["kid"], (None, frozenset()))
    if public is None or payload["kind"] not in may_sign:        # a kid we do not pin, or one that may not sign this kind
        raise Refused("key_signature")
    if sig is None or not ed25519.verify(base64.b64decode(public), pb, sig):
        raise Refused("key_signature")
    if payload["app"] != app:
        raise Refused("key_other_app")
    if payload["host"] != site:
        raise Refused("key_other_site")
    return payload


def _secrets(value) -> dict:
    if not isinstance(value, dict) or len(value) > SECRETS_MAX or not all(
            isinstance(k, str) and isinstance(v, str) and 0 < len(k) <= NAME_MAX and 0 < len(v) <= VALUE_MAX
            for k, v in value.items()):
        raise Refused("bad_request", 400)
    return dict(value)


def _site_and_key(header_site, body: dict, app: str, keys) -> tuple[str, dict]:
    site = site_of(header_site)
    if not site or body.get("site") != site:            # the body names the same site as the header, exactly
        raise Refused("bad_request", 400)
    return site, check_key(body.get("key"), app, site, keys)


def connect(store, app: str, header_site, body: dict, keys: dict | None = None) -> dict:
    """Store the shop the key names, with its secrets; a second connect keeps the old secrets as the previous set."""
    if not isinstance(body, dict):
        raise Refused("bad_request", 400)
    secrets = _secrets(body.get("secrets"))
    site = site_of(header_site)
    local = bool(site) and is_local(site)
    if local and not getattr(store, "local", False):    # a shop on this machine connects in local mode only
        raise Refused("bad_request", 400)
    if local and getattr(store, "local_keys", None):
        keys = {**(keys or LIBRARY_KEYS), **store.local_keys}
    site, payload = _site_and_key(header_site, body, app, keys)
    old = store.get(site)
    record = {"site": site, "url": f"{'http' if local else 'https'}://{site}", "secrets": secrets,
              "previous": (old or {}).get("secrets") or {}, "key_id": payload["id"], "kind": payload["kind"],
              "connected": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    store.put(site, record)
    return {"connected": site}


def disconnect(store, app: str, header_site, body: dict, keys: dict | None = None) -> dict:
    """Forget the shop the key names (the same key check as connect)."""
    if not isinstance(body, dict):
        raise Refused("bad_request", 400)
    site = site_of(header_site)
    if site and is_local(site) and getattr(store, "local", False) and getattr(store, "local_keys", None):
        keys = {**(keys or LIBRARY_KEYS), **store.local_keys}
    site, _ = _site_and_key(header_site, body, app, keys)
    store.delete(site)
    return {"disconnected": site}


def handle(store, app: str, path: str, headers, raw: bytes, keys: dict | None = None) -> tuple[int, dict]:
    """``POST /ivendnext/connect`` and ``/ivendnext/disconnect``: (status, answer). The key is the only credential."""
    try:
        body = json.loads(raw)
    except ValueError:
        return 400, {"refused": "bad_request"}
    try:
        step = connect if path == CONNECT else disconnect
        return 200, step(store, app, headers.get(SITE_HEADER), body, keys)
    except Refused as e:
        return e.status, {"refused": e.code}
    except Exception:               # noqa: BLE001 — the store did not answer: the site offers "Connect again"
        return 503, {"refused": "unavailable"}


def secrets_for(record: dict | None, name: str) -> list[bytes]:
    """The shop's current secret of that name, then its previous one: what a call to that route may be signed with."""
    if not record:
        return []
    return [s.encode() for s in ((record.get("secrets") or {}).get(name), (record.get("previous") or {}).get(name)) if s]


class FileStore:
    """The shops in one JSON file (tests, a laptop, your own server). Written whole, through a temporary file."""

    def __init__(self, path: str, local: bool = False, local_keys: dict | None = None):
        self.path, self._lock = path, threading.Lock()
        self.local, self.local_keys = local, local_keys or {}

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _write(self, data: dict):
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # secrets: readable by this user alone
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def get(self, site: str) -> dict | None:
        if not self.local and is_local(site):     # a shop local mode connected is never served outside local mode
            return None
        with self._lock:
            return self._read().get(site)

    def put(self, site: str, record: dict):
        with self._lock:
            data = self._read()
            data[site] = record
            self._write(data)

    def delete(self, site: str):
        with self._lock:
            data = self._read()
            if data.pop(site, None) is not None:
                self._write(data)

    def sites(self) -> list[str]:
        with self._lock:
            return sorted(n for n in self._read() if CLAIM_MARK not in n and (self.local or not is_local(n)))

    def claim(self, name: str, now: float, stale_s: float) -> bool:
        """Take ``name`` unless another call took it less than ``stale_s`` seconds ago (``TableStore.claim``; an expiry
        passed as ``now`` works the same way, ``function.Claimed``)."""
        with self._lock:
            data = self._read()
            if (data.get(name) or {}).get("at", 0) > now - stale_s:
                return False
            data[name] = {"at": now}
            self._write(data)
            return True


def open_store(env) -> object:
    """The table on CitiXsys hosting (``IVN_SHOPS_TABLE``), else the file (``IVN_SHOPS_FILE``), in local mode or not."""
    local = local_mode(env)
    if local and (env.get("IVN_SHOPS_TABLE") or "").strip():
        raise SystemExit("IVN_LOCAL is for your laptop: it never runs with IVN_SHOPS_TABLE (hosting)")
    if not local and (env.get("IVN_LOCAL_LIBRARY_KEYS") or "").strip():
        raise SystemExit("IVN_LOCAL_LIBRARY_KEYS is read in local mode only: set IVN_LOCAL=1 too")
    if (env.get("IVN_SHOPS_TABLE") or "").strip():
        import dynamo
        return dynamo.TableStore(env["IVN_SHOPS_TABLE"].strip(), env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"))
    if (env.get("IVN_SHOPS_FILE") or "").strip():
        path = (env.get("IVN_LOCAL_LIBRARY_KEYS") or "").strip()
        return FileStore(env["IVN_SHOPS_FILE"].strip(), local, local_keys(path) if path else None)
    raise SystemExit("IVN_LIBRARY_APP is set but no store is: set IVN_SHOPS_TABLE (hosting) or IVN_SHOPS_FILE")
