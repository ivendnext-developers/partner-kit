"""Run-time patches of platform code — the partner copy.

COPIED FROM ivendnext/iVendNext_PWA · ci/check_engine_attr_patch_allowlist.py @ 05bb4dab92f294edac7b9d5bbac697d3072a4978:
``_engine_bound_names``, ``_attr_base_name`` and ``find_patches`` (the detector), and its canaries. A defect in the
detector is a defect there: report it on Retail mPOS's board.

CHANGED FOR PARTNERS:
- the ALLOW-LIST is EMPTY: no partner app patches platform code, ever;
- ``ENGINE_ROOT`` (one package, ``ivendnext_pos``) becomes every platform package — the framework, the ERP, the
  engine, mPOS, payments, loyalty and the framework's alias;
- because the framework is now a root, ONE assignment shape is exempt: ``<frappe>.<state>.<name> = …`` — exactly one
  attribute below the framework's per-request state (``flags``, ``local``, ``response``, ``form_dict``, ``session``),
  on a name bound to the framework module itself. ``frappe.flags.x = True`` is state; ``frappe.local.db.sql = f``
  (deeper) and ``erp_module.session = …`` (not the framework) are patches and are flagged (review fold R8).
STATED BOUND (unchanged from the source): an indirection — a helper returning the module, ``sys.modules``,
``importlib`` — evades a static scan of this shape; a person's review covers deliberate evasion.
"""
from __future__ import annotations

import ast

ENGINE_ROOTS = ("frappe", "erpnext", "ivendnext_pos", "ivendnext_mpos", "ivendnext_payments_core",
                "ivend_loyality", "hw_integration", "ivendframework")
RUNTIME_STATE = ("flags", "local", "response", "form_dict", "session")


def _is_engine(module: str) -> bool:
    return any(module == r or module.startswith(r + ".") for r in ENGINE_ROOTS)


def _engine_bound_names(tree: ast.AST) -> set[str]:
    """Names this module binds from platform imports. A `from` import may bind a function rather than a module —
    still suspect: assigning an attribute on an imported engine FUNCTION is a patch-shaped act too."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_engine(alias.name):
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _is_engine(node.module):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
    return names


def _attr_base_name(node: ast.expr) -> str | None:
    """The root Name of a (possibly chained) attribute expression."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _is_runtime_state(t: ast.Attribute, framework_names: set[str]) -> bool:
    """``frappe.flags.x = …``: the framework's per-request state, not a patch (partner change; see the header)."""
    chain = []
    node: ast.expr = t
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    chain.reverse()
    return isinstance(node, ast.Name) and node.id in framework_names and len(chain) == 2 and chain[0] in RUNTIME_STATE


def _framework_names(tree: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.asname or a.name for a in node.names if a.name == "frappe"}
    return out


def find_patches(source: str, path_label: str) -> list[str]:
    """Every engine-attr patch site in one file's source, as findings."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"{path_label}: unparseable ({e})"]
    bound = _engine_bound_names(tree)
    if not bound:
        return []
    framework = _framework_names(tree)
    findings = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "setattr" and node.args:
                base = _attr_base_name(node.args[0])
                if base in bound:
                    findings.append(
                        f"{path_label}:{node.lineno}: setattr on engine-bound '{base}'"
                    )
            continue
        for t in targets:
            if isinstance(t, ast.Attribute):
                base = _attr_base_name(t)
                if base in bound and not _is_runtime_state(t, framework):
                    findings.append(
                        f"{path_label}:{t.lineno}: attribute assignment on "
                        f"engine-bound '{base}' ({ast.unparse(t)})"
                    )
    return findings


CANARY = """
from ivendnext_pos.ivendnext_pos.doc_events import pos_closing_validations

def sneak():
    pos_closing_validations.get_pos_invoices = sneak
"""

CANARY_SETATTR = """
import ivendnext_pos.ivendnext_pos.doc_events.pos_closing_validations as pcv

setattr(pcv, "get_pos_invoices", None)
"""

CLEAN = """
import frappe
from ivendnext_pos.ivendnext_pos.doc_events.pos_closing_validations import get_pos_invoices

def uses():
    rows = get_pos_invoices(1, 2, 3, 4)
    local = object()
    local.attr = rows  # non-engine attribute assignment — never flagged
    frappe.flags.in_pp_test = True  # framework run-time state — never flagged (partner change)
    return rows
"""
