"""The S2 service's only door into iVendNext: the record API, as the integration user (token key:secret).

Every call here is one of the request collection's calls (api/collection/: records read and written, a stock
balance, a till profile, a stock movement created and booked in one call), so a partner in any other language
makes the same requests. Standard library only. (Same shape as samples/s1_warranty/service/tenant.py.)
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request


class TenantError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class Tenant:
    def __init__(self, base: str, key: str, secret: str, timeout: float = 8):
        self.base, self.timeout = base.rstrip("/"), timeout
        self._auth = f"token {key}:{secret}"

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = f"{self.base}/api/resource/{urllib.parse.quote(path)}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}").get("data")
        except urllib.error.HTTPError as e:
            raise TenantError(f"{method} {path} -> HTTP {e.code}", e.code) from None
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as e:
            raise TenantError(f"{method} {path} -> {e}") from None

    def get(self, doctype, name):
        return self._call("GET", f"{doctype}/{name}")

    def list(self, doctype, fields, filters, order_by="modified asc", limit=200):
        return self._call("GET", doctype, {"fields": fields, "filters": filters, "order_by": order_by,
                                           "limit_page_length": str(limit)})

    def insert(self, doctype, body):
        return self._call("POST", doctype, body=body)

    def update(self, doctype, name, body):
        return self._call("PUT", f"{doctype}/{name}", body=body)

    def stock_balance(self, item, warehouse) -> float:
        rows = self.list("Bin", ["actual_qty"], [["item_code", "=", item], ["warehouse", "=", warehouse]])
        return float(rows[0]["actual_qty"]) if rows else 0.0

    def selling_warehouse(self, pos_profile) -> str:
        return self.get("POS Profile", pos_profile)["warehouse"]

    def transfer(self, company, item, qty, from_wh, to_wh) -> dict:
        """The engine's own Stock Entry, created AND booked in one call (docstatus 1). ``purpose`` is sent: over the
        API it is not derived from the entry type (measured)."""
        return self.insert("Stock Entry", {"stock_entry_type": "Material Transfer", "purpose": "Material Transfer",
                                           "company": company, "docstatus": 1,
                                           "items": [{"item_code": item, "qty": qty, "s_warehouse": from_wh,
                                                      "t_warehouse": to_wh}]})
