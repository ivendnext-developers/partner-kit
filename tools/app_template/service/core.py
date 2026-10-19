"""The app's logic, with nothing from iVendNext or the web in it: ``answer(context) -> the till's answer``.

Replace this with your own. It is pure, so a unit test needs no shop and no server (see tests/test_app.py).
The answer is the remote till key's closed vocabulary: a message (title up to 60 characters, body up to 280, level
``info`` · ``success`` · ``warning``). Never a price, a discount, a tax or a total (guide chapter 3).
"""

TITLE_MAX, BODY_MAX = 60, 280


def answer(context: dict) -> dict:
    lines = (context or {}).get("lines") or []
    n = len(lines)
    body = "There are no items on this sale yet." if n == 0 else f"This sale has {n} line{'s' if n != 1 else ''}."
    return {"message": {"title": "Hello", "body": body[:BODY_MAX], "level": "info"}}
