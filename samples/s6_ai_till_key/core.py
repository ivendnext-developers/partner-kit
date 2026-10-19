"""S6 — the AI till key: the pure core. Imports nothing from iVendNext and nothing from any AI provider.

    consent_text()            the words the shop reads before it switches the key on — built from CONTEXT_FIELDS and SENT_FIELDS
    build_prompt(context)     the prompt for the model — built from SENT_FIELDS and nothing else
    message_from(text)        the model's reply → the till's answer: a message, title <= 60, body <= 280, never more

``context`` is the till's own (recipes/point_handler.md): lines, customer, store, operator ... Only what SENT_FIELDS
names ever leaves the shop for the model; a test builds a context full of sentinel values and proves the rest never
reaches the prompt. The consent text is made from the same table, so the words and the data cannot drift apart.
"""

import re

TITLE_MAX, BODY_MAX = 60, 280
TITLE = "Suggestion"      # the message's title; the till's sheet already carries the key's own label ("AI tip"), so this must not repeat it

# field → (how the consent text names it, how the prompt shows it). THE one list of what is sent.
SENT_FIELDS = {
    "lines": "the item codes and quantities on the sale",
    "store": "the name of the store",
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


# What the TILL sends this service on every press (its context, recipes/point_handler.md step 1) — the first thing a shop
# consents to. The bench test fails if the real context ever carries a key that is not listed here.
CONTEXT_FIELDS = {
    "lines": "the item codes, quantities, units and a reference for each line of the sale", "store": "the store", "customer": "the customer on the sale, if any",
    "operator": "the cashier", "sale_ref": "the sale's reference", "pos_profile": "the register's profile",
    "company": "the company", "currency": "the currency",
}


def consent_text() -> str:
    """Two sentences: what the till sends this service, and the smaller part the service forwards to the AI model."""
    till = "; ".join(CONTEXT_FIELDS.values())
    ai = "; ".join(SENT_FIELDS.values())
    return (f"This key sends the following to the service at the address you set: {till}. It sends no prices, totals or payment "
            f"details. The service forwards only this to the AI model you set up: {ai}. The answer is shown to the cashier as a "
            f"message; it never changes the sale.")


def build_prompt(context: dict) -> str:
    lines = []
    for line in (context.get("lines") or [])[:30]:                  # a long basket is cut: the prompt stays small
        code = _CONTROL.sub(" ", str(line.get("item_code") or ""))[:80]
        qty = line.get("qty")
        lines.append(f"- {code} x {qty:g}" if isinstance(qty, (int, float)) else f"- {code}")
    store = _CONTROL.sub(" ", str(context.get("store") or "the store"))[:80]
    return ("You help a shop cashier. Items on the sale at " + store + ":\n" + "\n".join(lines) +
            "\nGive ONE short tip for the cashier (an add-on to suggest or a care note), in plain text, "
            "at most 40 words. Do not mention prices.")


def message_from(text) -> dict:
    """The model's reply as the till's answer. Control characters out, spaces collapsed, cut at a word at 280."""
    body = " ".join(_CONTROL.sub(" ", str(text or "")).split())
    if not body:
        raise ValueError("empty reply")
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return {"message": {"title": TITLE, "body": body, "level": "info"}}


def answer(context: dict, provider) -> dict:
    """The whole binding: prompt → the customer's provider → the till's answer. ``provider(prompt) -> str``."""
    return message_from(provider(build_prompt(context)))
