"""S26 — the rules of a derived price list, with no network and no shop: Python 3.9+, standard library only.

A rule says: every price on the TARGET list is the price on the SOURCE list times FACTOR plus OFFSET, rounded to STEP
in DIRECTION, never below FLOOR, at the rule's DECIMAL PLACES (the shop's currency precision). Money is ``Decimal`` from end to end; a float never touches a price.

    rate = max(round_to_step(source × factor + offset), floor)

Everything here is pure, so the laptop tests prove the arithmetic and the rule checks without a shop.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation

STEPS = ("0.01", "0.05", "0.5", "1")
DIRECTIONS = {"Nearest": ROUND_HALF_UP, "Up": ROUND_CEILING, "Down": ROUND_FLOOR}
STAMP = "PP-DPL"          # a price row the service made carries "PP-DPL <rule> <source row>" in its note


def D(v) -> Decimal:
    """A price as a Decimal, through its text: 1.1 stays 1.1, never 1.100000000000000088817841970012523."""
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except InvalidOperation:
        raise ValueError(f"not a number: {v!r}") from None


def _decimals(v: Decimal) -> int:
    return max(-v.normalize().as_tuple().exponent, 0)


class Rule:
    """One PP DPL Rule record, read from the shop. ``problems`` lists why it cannot run (empty: it can)."""

    def __init__(self, raw: dict):
        self.name = raw["name"]
        self.source, self.target = raw.get("source_price_list") or "", raw.get("target_price_list") or ""
        self.enabled = bool(int(raw.get("enabled") or 0))
        self.problems: list[str] = []
        try:
            self.factor, self.offset, self.floor = D(raw.get("factor")), D(raw.get("offset")), D(raw.get("floor"))
        except ValueError as e:
            self.factor = self.offset = self.floor = Decimal(0)
            self.problems.append(str(e))
        self.step = str(raw.get("rounding_step") or "0.01")
        dp = raw.get("decimal_places")
        self.places = int(dp) if dp not in (None, "") else 2
        self.direction = raw.get("rounding") or "Nearest"
        if self.factor <= 0:
            self.problems.append("the factor must be above 0")
        if self.floor < 0:
            self.problems.append("the floor must not be below 0")
        if self.step not in STEPS:
            self.problems.append(f"the rounding step must be one of {', '.join(STEPS)}")
        if not 0 <= self.places <= 6:
            self.problems.append("the decimal places must be 0 to 6")
        if self.direction not in DIRECTIONS:
            self.problems.append("the rounding must be Nearest, Up or Down")
        if not self.source or not self.target:
            self.problems.append("the rule names no source or no target list")
        elif self.source == self.target:
            self.problems.append("the source and the target are the same list")

    def fingerprint(self) -> str:
        """What a backfill depends on: change any of these and every target price is worked out again."""
        return "|".join(map(str, (self.source, self.target, self.factor, self.offset, self.step, self.direction, self.floor, self.places)))


def derive(source_rate, rule: Rule) -> tuple[Decimal, bool]:
    """The target price for one source price, and whether the floor raised it, at the rule's decimal places."""
    raw = D(source_rate) * rule.factor + rule.offset
    step = Decimal(rule.step)
    rate = (raw / step).to_integral_value(rounding=DIRECTIONS[rule.direction]) * step
    raised = rate < rule.floor or (rate == 0 and rate.is_signed())     # -0.00: a negative result rounded to zero
    rate = max(rate, rule.floor) + 0                                      # + 0 clears the sign of a -0.00
    return rate.quantize(Decimal(1).scaleb(-rule.places), rounding=ROUND_HALF_UP), raised


def usable(raw_rules: list[dict], currency: dict[str, str]) -> tuple[dict[str, Rule], list[dict]]:
    """The enabled rules that may run, and every refused one with its reason. ``currency`` is per list name (a list the
    shop does not have is missing). Refused: a rule's own problems; two lists in different currencies; a step or floor
    finer than the rule's decimal places; two rules writing one target list; a loop."""
    refused, ok = [], {}
    for r in (Rule(x) for x in raw_rules):
        if not r.enabled:
            continue
        why = list(r.problems)
        if not why:
            if r.source not in currency or r.target not in currency:
                why.append("a list the rule names is not in the shop")
            elif currency[r.source] != currency[r.target]:
                why.append(f"the lists are in different currencies ({currency[r.source]}, {currency[r.target]})")
            elif max(_decimals(Decimal(r.step)), _decimals(r.floor)) > r.places:
                why.append(f"the rounding step or the floor is finer than {r.places} decimal places")
        if why:
            refused.append({"rule": r.name, "why": "; ".join(why)})
        else:
            ok[r.name] = r
    by_target: dict[str, list[str]] = {}
    for r in ok.values():
        by_target.setdefault(r.target, []).append(r.name)
    for target, names in by_target.items():
        if len(names) > 1:
            for n in names:
                refused.append({"rule": n, "why": f"{len(names)} rules write {target}: one list has one rule"})
                ok.pop(n)
    for n in [n for n in ok if _closes_a_loop(ok, ok[n])]:
        refused.append({"rule": n, "why": "the rule closes a loop of lists (a list worked out, in the end, from itself)"})
    for r in refused:
        ok.pop(r["rule"], None)
    return ok, refused


def _closes_a_loop(rules: dict[str, Rule], rule: Rule) -> bool:
    """True when following the rules on from this rule's target reaches its source again."""
    seen, todo = set(), [rule.target]
    while todo:
        lst = todo.pop()
        if lst == rule.source:
            return True
        if lst in seen:
            continue
        seen.add(lst)
        todo += [r.target for r in rules.values() if r.source == lst]
    return False


def stamp(rule: str, source_row: str) -> str:
    return f"{STAMP} {rule} {source_row}"


def stamped_by(note: str | None, rule: str) -> bool:
    """True when the note is this rule's stamp (for any source row)."""
    return (note or "").startswith(f"{STAMP} {rule} ")


def general(row: dict) -> bool:
    """A price row for everyone: no customer, no supplier, no batch. Only these are derived."""
    return not (row.get("customer") or row.get("supplier") or row.get("batch_no"))
