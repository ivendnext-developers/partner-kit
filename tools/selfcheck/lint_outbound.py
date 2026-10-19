"""Outbound calls — the partner copy.

COPIED FROM ivendnext/ivendnext_integration_core · ci/check_no_outbound_calls.py @ origin/development
2dc12a22908f1e1cdc61d09608df258fc3f27c1a: ``BANNED_ROOTS``, ``BANNED_FRAPPE_ATTRS``, ``_dotted``, the AST walk of
``scan_source`` and its fixtures. A defect in them is a defect there: report it on Integration Core's board.

CHANGED FOR PARTNERS:
- Integration Core forbids EVERY outbound import and has no allow-list. A partner app may need to call its own
  service, so the partner copy adds one: ``partner_outbound_hosts = ["api.example.com", ...]`` in ``hooks.py``.
  - No declaration: any transport import or framework egress = FAIL (as the source).
  - A declaration: transport use is REVIEW (a person checks every call goes to a declared host), and any URL literal
    in the code whose host is NOT declared = FAIL.
- ``frappe.sendmail`` moves from FAIL to REVIEW: it queues mail through the shop's OWN email account, to recipients
  the shop sets. A person checks where the recipients come from.
STATED BOUND (from the source): a dynamically-built import, a subprocess, or a URL assembled at run time is not seen
by a static scan. And, as the source says of ``BANNED_FRAPPE_ATTRS``: it is a DENY-list inside an allow-listed
framework, so it is inherently incomplete — a framework egress helper not on it passes (review fold R11).
"""
from __future__ import annotations

import ast
import re
from urllib.parse import urlparse

#: Transport module roots. A dotted import is matched on its FIRST component, so
#: `urllib.request` and `urllib3.util` are both caught by their roots.
BANNED_ROOTS = frozenset(
    {
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urllib3",
        "http",  # http.client
        "socket",
        "socketserver",
        "ftplib",
        "smtplib",
        "telnetlib",
        "poplib",
        "imaplib",
        "paramiko",
        "websocket",
        "websockets",
        "pycurl",
        "xmlrpc",
        "suds",
        "zeep",
    }
)

BANNED_FRAPPE_ATTRS = (
    "frappe.integrations.utils.make_get_request",
    "frappe.integrations.utils.make_post_request",
    "frappe.integrations.utils.make_put_request",
    "frappe.integrations.utils.make_request",
    "frappe.utils.file_manager.download_file",
    "frappe.utils.get_request_session",
    "frappe.utils.has_gravatar",
)
#: partner change: mail through the shop's own account is REVIEW, not FAIL
REVIEW_FRAPPE_ATTRS = ("frappe.sendmail",)

URL_RE = re.compile(r"""https?://[^\s"'<>]+""")


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def scan_source(source: str, path: str) -> list[tuple[str, int, str]]:
    """``[(kind, line, what)]`` with kind ``transport`` · ``egress`` · ``mail`` · ``url:<host>``."""
    findings: list[tuple[str, int, str]] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [("transport", exc.lineno or 0, f"could not parse: {exc.msg}")]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_ROOTS:
                    findings.append(("transport", node.lineno, f"imports transport module {alias.name!r}"))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}" if node.module else alias.name
                if dotted in BANNED_FRAPPE_ATTRS:
                    findings.append(("egress", node.lineno, f"imports frappe egress {dotted!r}"))
                elif dotted in REVIEW_FRAPPE_ATTRS:
                    findings.append(("mail", node.lineno, f"imports {dotted!r}"))
            if node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root in BANNED_ROOTS:
                    findings.append(("transport", node.lineno, f"imports from transport module {node.module!r}"))
        elif isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted in BANNED_FRAPPE_ATTRS:
                findings.append(("egress", node.lineno, f"calls frappe egress {dotted!r}"))
            elif dotted in REVIEW_FRAPPE_ATTRS:
                findings.append(("mail", node.lineno, f"calls {dotted!r} (mail through the shop's own account)"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for url in URL_RE.findall(node.value):
                host = (urlparse(url).hostname or "").lower()
                if host:
                    findings.append((f"url:{host}", node.lineno, f"names the URL {url[:80]!r}"))
    return findings


def verdict(findings: list[tuple[str, str, int, str]], declared_hosts: list[str] | None) -> tuple[str, list[str]]:
    """``findings`` = [(path, kind, line, what)] over the whole app. Returns (status, lines)."""
    hosts = {h.lower() for h in (declared_hosts or [])}
    fails, reviews = [], []
    uses_transport = any(k in ("transport", "egress") for _, k, _, _ in findings)
    for path, kind, line, what in findings:
        where = f"{path}:{line}: {what}"
        if kind in ("transport", "egress"):
            (reviews if hosts else fails).append(where + ("" if hosts else " — no partner_outbound_hosts declared"))
        elif kind == "mail":
            reviews.append(where)
        elif kind.startswith("url:") and uses_transport:
            host = kind[4:]
            if host not in hosts and not any(host.endswith("." + h) for h in hosts):
                fails.append(where + f" — host {host!r} is not in partner_outbound_hosts {sorted(hosts)}")
    return ("FAIL" if fails else "REVIEW" if reviews else "PASS"), fails + reviews


# ── fixtures (copied from the source, plus the allow-list's own) ─────────────
FIXTURES = {
    "top-level import": "import requests\n",
    "from-import": "from requests import get\n",
    "FUNCTION-LOCAL import (the one a regex misses)": (
        "def send(payload):\n"
        "    import requests\n"
        "    return requests.post('https://example.test', json=payload)\n"
    ),
    "aliased import": "import urllib3 as u3\n",
    "stdlib socket": "import socket\n",
    "dotted stdlib": "import http.client\n",
    "frappe egress: the session FACTORY": (
        "import frappe\n"
        "def push(body):\n"
        "    s = frappe.utils.get_request_session()\n"
        "    return s.post('https://example.test', json=body)\n"
    ),
    "frappe egress: make_post_request": (
        "import frappe\n"
        "def go():\n"
        "    return frappe.integrations.utils.make_post_request('https://example.test')\n"
    ),
}
CLEAN_FIXTURES = {
    "our own imports": "import frappe\nfrom frappe.utils import cint\n",
    "a relative import": "from . import states\n",
    "a variable that merely looks like one": "requests = 3\nprint(requests)\n",
    "a local named socket": "def f():\n    socket = 1\n    return socket\n",
}
