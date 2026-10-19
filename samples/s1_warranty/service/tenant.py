"""The service's only door into iVendNext: the record API, as the integration user (token key:secret).

Every call here is one of the request collection's calls (api/collection/), so a partner in any other
language makes the same requests. Standard library only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

MARK = "pp_wrc warranty sample"   # the Comment's signature line — how the service finds its own comment


class TenantError(Exception):
    pass


class Tenant:
    def __init__(self, base: str, key: str, secret: str, timeout: float = 8):   # under the webhook's 10 s timeout
        self.base, self.timeout = base.rstrip("/"), timeout
        self._auth = f"token {key}:{secret}"

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/{urllib.parse.quote(path)}"
        if params:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, str) else v for k, v in params.items()})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise TenantError(f"{method} {path} -> HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise TenantError(f"{method} {path} -> {e}") from None

    def get(self, doctype: str, name: str) -> dict:
        return self._call("GET", f"{doctype}/{name}")["data"]

    def list(self, doctype: str, fields: list, filters: list, order_by: str = "modified asc", limit: int = 100) -> list:
        return self._call("GET", doctype, {"fields": fields, "filters": filters, "order_by": order_by,
                                           "limit_page_length": str(limit)})["data"]

    def item_groups(self, codes: list[str]) -> dict:
        """``{item_code: item_group}`` for the codes that exist. A code that is not an Item is simply absent."""
        if not codes:
            return {}
        rows = self.list("Item", ["name", "item_group"], [["name", "in", sorted(set(codes))]], "name asc", 500)
        return {r["name"]: r["item_group"] for r in rows}

    def serials_of(self, row: dict) -> list[str]:
        """A sale line's serial numbers: from its Serial and Batch Bundle, else from the line's text field."""
        if row.get("serial_and_batch_bundle"):
            bundle = self.get("Serial and Batch Bundle", row["serial_and_batch_bundle"])
            return [e["serial_no"] for e in bundle.get("entries") or [] if e.get("serial_no")]
        return [s.strip() for s in (row.get("serial_no") or "").splitlines() if s.strip()]

    def has_our_comment(self, doctype: str, name: str) -> bool:
        rows = self.list("Comment", ["name"], [["reference_doctype", "=", doctype], ["reference_name", "=", name],
                                               ["comment_type", "=", "Comment"], ["content", "like", f"%{MARK}%"]],
                         "creation asc", 1)
        return bool(rows)

    def add_comment(self, doctype: str, name: str, text: str) -> str:
        html = "<br>".join(line.replace("&", "&amp;").replace("<", "&lt;") for line in text.splitlines())
        doc = self._call("POST", "Comment", body={"comment_type": "Comment", "reference_doctype": doctype,
                                                  "reference_name": name, "content": html})["data"]
        return doc["name"]
