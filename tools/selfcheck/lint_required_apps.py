"""required_apps provenance — the partner copy.

COPIED FROM ivendnext/iVendNext_PWA · ci/check_foreign_apps.py @ 05bb4dab92f294edac7b9d5bbac697d3072a4978:
``parse_required_apps``, ``_required_app_name`` and ``_required_app_org`` are byte copies. A defect in them is a defect
there: report it on Retail mPOS's board.

CHANGED FOR PARTNERS (the gate around them):
- mPOS demands required_apps resolve to EXACTLY its own four apps. A partner app declares what IT needs, so the rule
  is: a literal required_apps must exist (absent, commented out or computed = FAIL); an org-qualified entry naming
  any org but ``ivendnext`` = FAIL (the upstream pull this lint exists to refuse); a bare name outside the platform
  = REVIEW (another app the reviewer must know); and every platform package the code IMPORTS must be declared
  (an undeclared dependency = FAIL — the app installs on a site that may not carry it);
- a BARE entry (``"frappe"``) = FAIL: at the framework pin ``parse_app_name`` sends every bare name to ``find_org``,
  which asks GitHub which org owns it — offline or rate-limited, the install dies with a message-less
  ``InvalidRemoteException`` (measured on our test bench; the source lint's own docstring warns of it).
  Write ``"ivendnext/<app>"``: only the last segment names the app, and no network call is made.
- Gate 2 (git provenance of sibling app checkouts) is dropped: a partner's app directory has no bench beside it.
"""
from __future__ import annotations

import ast

OWN_ORG = "ivendnext"
# the platform apps a partner app may declare, by the name the framework resolves them to
PLATFORM_APPS = ("frappe", "erpnext", "ivendnext_pos", "ivendnext_mpos", "ivendnext_payments_core",
                 "ivend_loyality", "hw_integration")


def parse_required_apps(src: str) -> list[str] | None:
    """Return the EFFECTIVE module-level required_apps, or None if absent/dynamic."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    effective: list | None = None
    seen = False
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(isinstance(t, ast.Name) and t.id == "required_apps" for t in targets):
                continue
            seen = True
            if node.value is None:
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if not isinstance(value, (list, tuple)):
                return None
            effective = list(value)
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "required_apps"
        ):
            seen = True
            if not isinstance(node.op, ast.Add) or effective is None:
                return None
            try:
                rhs = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if not isinstance(rhs, (list, tuple)):
                return None
            effective = effective + list(rhs)
    return effective if seen else None


def _required_app_name(entry: str) -> str:
    """The app name the framework will resolve a required_apps entry to.

    Mirrors ``frappe.installer.parse_required_app_name`` deliberately — an entry may
    be a bare name, ``org/repo``, a git URL, and may carry an ``@branch`` or ``#ref``;
    the framework keys the install off the LAST path segment either way. Comparing the
    literal string instead is what would make ``ivendnext/ivendnext_pos`` read as a
    foreign app.
    """
    name = entry.strip().rstrip("/").split("#")[0]
    name = name.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name.split("@")[0].removesuffix(".git")


def _required_app_org(entry: str) -> str | None:
    """The org an org-qualified entry names, or None for a bare app name.

    ``ivendnext/ivendnext_pos`` -> ``ivendnext``; ``frappe/erpnext`` -> ``frappe``;
    ``https://github.com/frappe/erpnext.git`` -> ``frappe``; ``erpnext`` -> None.
    """
    text = entry.strip().rstrip("/").split("#")[0].removesuffix(".git")
    if "/" not in text:
        return None
    head = text.rsplit("/", 1)[0]
    return head.rsplit("/", 1)[-1].rsplit(":", 1)[-1] or None


def check(hooks_src: str, imported_platform: set[str], app_name: str) -> tuple[str, list[str]]:
    """(status, findings). ``imported_platform`` = the platform app names the app's code imports."""
    declared = parse_required_apps(hooks_src)
    if declared is None:
        return "FAIL", ["no literal required_apps in hooks.py (absent, commented out or computed): the app's "
                        "dependencies are undeclared, so it can install on a site that lacks them"]
    resolved = {_required_app_name(a) for a in declared}
    fails, reviews = [], []
    for a in declared:
        org = _required_app_org(a)
        if org is not None and org.lower() != OWN_ORG:
            fails.append(f"required_apps entry {a!r} names the org {org!r}: only {OWN_ORG!r} may be named")
        elif org is None and "://" not in a and not a.startswith("git@"):
            fails.append(f"required_apps entry {a!r} is a bare name: the install asks GitHub who owns it and fails "
                         f"offline or rate-limited — write 'ivendnext/{_required_app_name(a)}'")
        elif _required_app_name(a) not in PLATFORM_APPS:
            reviews.append(f"required_apps entry {a!r} is not a platform app: a reviewer confirms it")
    for app in sorted(imported_platform - resolved - {app_name}):
        fails.append(f"the code imports {app!r} but required_apps does not declare it (declared: {declared})")
    return ("FAIL" if fails else "REVIEW" if reviews else "PASS"), fails + reviews
