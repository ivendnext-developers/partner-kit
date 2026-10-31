"""Run your own server for ONE shop: the fallback way to give a service its secrets.

Every sample with a service connects itself by default (many shops, ``shops.py``): the site hands each point's secret to
the app at install, and the app keeps it per site. A partner who runs the service on their own server for a single shop
may instead set the secrets by hand, in the names each sample has always used (``IVN_POINT_SECRET``, ``PP_POINT_SECRET``,
``IVN_CHECK_SECRET``, ``IVN_SCAN_SECRET``, ``IVN_SECRET_<KEY>``, the shop's address and the integration user's key). This
is the one place those names are read, so every sample reads them the same way:

    if oneshop.many(conf):                       # IVN_LIBRARY_APP is set: the shops connect themselves
        ...
    else:
        one = oneshop.settings(conf, ["IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"])

``settings`` answers {name: value} with each value stripped, and stops the service with one plain line naming every
missing setting, and the many-shops way, when one is not set. Standard library only.
"""
from __future__ import annotations

MANY = "IVN_LIBRARY_APP"


def value(conf, name: str) -> str:
    """The setting's value, stripped; "" when it is not set."""
    v = conf.get(name) if conf is not None else None
    return v.strip() if isinstance(v, str) else ""


def many(conf) -> bool:
    """Whether the service runs for many shops (they connect themselves): the default for every hosted app."""
    return bool(value(conf, MANY))


def settings(conf, names, optional=()) -> dict:
    """The one-shop settings ``names`` (all required) and ``optional`` (may be empty), or SystemExit naming what is missing."""
    missing = [n for n in names if not value(conf, n)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} (one shop, on your own server), or {MANY} with a shops store "
                         "(many shops: each connects itself after it installs the app)")
    return {n: value(conf, n) for n in (*names, *optional)}
