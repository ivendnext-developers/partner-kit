"""S63 — the Mews adapter (Connector API), the reference for your own. Mews' Demo environment is open to developers.

The store's *Connection* box holds ``client_token``, ``access_token``, ``service_id`` (the Mews service the orders go to) and,
while you try it, ``environment=demo``. *Charge code* and *Tip code* are Mews accounting category ids.

Three things Mews leaves to the caller:
  * The *No Post* classification (``Cashlist``) does not block an order, so this adapter reads it at the check, on the guest who
    signs, and again at the post, on the reservation's owner, whose refusal goes to the auditor.
  * A posted item cannot be cancelled: a return is a negative line.
  * An order has no idempotency key, so a call whose answer was lost goes to the auditor (``HotelLost``), never again to Mews.
"""

from __future__ import annotations

from hotel import Deadline, HotelDown, HotelLost, HotelRefused, NoGuest, call_json, parse_connection

BASE = {"demo": "https://api.mews-demo.com", "": "https://api.mews.com", "production": "https://api.mews.com"}
NO_POST = "Cashlist"
STAYING = "Started"


class Mews:
    def __init__(self, conf: dict, s: dict, timeout: float):
        c = parse_connection(s["connection"])
        if not (c.get("client_token") and c.get("access_token") and c.get("service_id")):
            raise HotelRefused("This store's Mews connection needs client_token, access_token and service_id.")
        self.base = BASE.get(c.get("environment", "").lower(), BASE[""])
        self.service, self.timeout = c["service_id"], timeout
        self.auth = {"ClientToken": c["client_token"], "AccessToken": c["access_token"], "Client": "iVendNext Room Charge 1.0"}

    def _call(self, op: str, body: dict, timeout: float) -> dict:
        code, out = call_json(f"{self.base}/api/connector/v1/{op}", {**self.auth, **body}, timeout)
        if code == 401:                         # a token the hotel can fix: the charge waits. A 403 is Mews' own refusal
            raise HotelDown("Mews refused our key (401): check the store's connection")
        if code >= 400:
            raise HotelRefused(str(out.get("Message") or f"Mews refused it ({code})."))
        return out

    def _ask(self, op: str, body: dict, deadline: Deadline) -> dict:
        try:
            return self._call(op, body, deadline.left())
        except HotelLost as e:                  # a question moved nothing: as good as no answer
            raise HotelDown(str(e)) from None

    def find(self, room: str, guest: str) -> str:
        deadline, surname = Deadline(self.timeout), guest.casefold()
        rooms = self._ask("resources/getAll", {"Names": [room], "Extent": {"Resources": True}, "Limitation": {"Count": 10}}, deadline)
        known = [r["Id"] for r in rooms.get("Resources") or [] if (r.get("Name") or "").casefold() == room.casefold()]
        if not known:
            raise NoGuest(f"There is no room {room} at this hotel.")
        for resource in known:
            answer = self._ask("customers/search", {"ResourceId": resource, "Extent": {"Customers": True}}, deadline)
            for hit in answer.get("Customers") or []:
                person, stay = hit.get("Customer") or {}, hit.get("Reservation") or {}
                if stay.get("State") == STAYING and (person.get("LastName") or "").casefold() == surname:
                    if NO_POST in (person.get("Classifications") or []):
                        raise NoGuest(f"Room {room} can't take charges. Ask for another way to pay.")
                    return stay["Id"]
        raise NoGuest(f"Room {room} has no guest named {guest}.")

    def _payer(self, folio: str, deadline: Deadline) -> str:
        """The reservation's owner, read at the post: a guest who has left or gone on the No Post list is refused here."""
        got = self._ask("reservations/getAll/2023-06-06", {"ReservationIds": [folio], "Limitation": {"Count": 1}}, deadline)
        stays = got.get("Reservations") or []
        if not stays or stays[0].get("State") != STAYING:
            raise HotelRefused("This guest is no longer staying.")
        account = stays[0]["AccountId"]
        people = self._ask("customers/getAll", {"CustomerIds": [account], "Extent": {"Customers": True}, "Limitation": {"Count": 1}},
                           deadline).get("Customers") or []
        if people and NO_POST in (people[0].get("Classifications") or []):
            raise HotelRefused("This guest is on the hotel's No Post list.")
        return account

    def post(self, folio: str, lines: list[dict], receipt: str, currency: str) -> list[str]:
        account = self._payer(folio, Deadline(self.timeout))
        items = [{"Name": ln["label"], "UnitCount": 1, "AccountingCategoryId": ln["code"], "ExternalIdentifier": f"{receipt}-{ln['kind']}",
                  "UnitAmount": {"Currency": currency, "GrossValue": ln["amount"], "TaxCodes": []}} for ln in lines]
        out = self._call("orders/add", {"ServiceId": self.service, "AccountId": account, "LinkedReservationId": folio,
                                        "Notes": f"Receipt {receipt}", "Items": items}, self.timeout)
        return [f"{out['OrderId']}#{i + 1}" for i in range(len(lines))]


__all__ = ["Mews", "HotelDown"]
