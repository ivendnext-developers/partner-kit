"""S34's stand-in ERP: the three questions the sample asks an ERP, answered from ``erp_standin.json``.

Replace ``StandIn`` with a client of your ERP that has the same three methods. Each must answer well inside the
subscription's time to answer (3 seconds): the purchase order's save waits for you, its record locked.
"""

from __future__ import annotations

import json
import pathlib
import threading


class StandIn:
    def __init__(self, path: str | pathlib.Path | None = None):
        path = path or pathlib.Path(__file__).with_name("erp_standin.json")
        self.data = json.loads(pathlib.Path(path).read_text("utf-8"))
        self.numbers: dict[str, str] = {}
        self.lock = threading.Lock()

    def supplier_hold(self, supplier: str) -> str | None:
        """Why the ERP holds this supplier, or None."""
        return (self.data.get("held_suppliers") or {}).get(supplier)

    def budget_left(self, company: str | None, currency: str) -> int | None:
        """What the company may still order this month, in minor units of ``currency``; None when no budget is set."""
        budgets = self.data.get("monthly_budgets") or {}
        mine = budgets.get(company or "") or budgets.get("*") or {}
        if currency not in mine:
            return None
        spent = ((self.data.get("ordered_this_month") or {}).get(company or "") or {}).get(currency, 0)
        return mine[currency] - spent

    def order_number(self, po_name: str) -> str:
        """The ERP's own number for this order: the same number every time the same order asks."""
        with self.lock:
            if po_name not in self.numbers:
                self.numbers[po_name] = f"{self.data.get('number_prefix', 'ERP-PO-')}{self.data.get('first_number', 1) + len(self.numbers)}"
            return self.numbers[po_name]
