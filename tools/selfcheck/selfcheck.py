#!/usr/bin/env python3
"""selfcheck — the intake check for an app that runs inside a shop, run before it is submitted. Only the CitiXsys
Consulting Team builds such an app, where no extension point fits; a partner keeps rule 3 (guide chapter 3: your code
runs on your server) and ships data, which the manifest check covers. Read-only: it never imports or runs the app, it reads its files.

    python3 tools/selfcheck/selfcheck.py <app-dir> [--prefix "PP PDA"] [--manifest <manifest.json>] [--json <out>]
    python3 tools/selfcheck/selfcheck.py --self-test

One line per check: PASS, FAIL or REVIEW (a person looks). Exit 1 on any FAIL, else 0. ``<app-dir>`` is the app's
repository folder (the one holding the package with ``hooks.py``) or the package itself.

Three checks are COPIES of our own CI lints, each with its source in its header (``lint_required_apps.py``,
``lint_engine_patch.py``, ``lint_outbound.py``). The rest are new; each finding's own message says what it means
and how to fix it. ``--self-test`` plants each check's defect in a temporary app and proves the check fires, and runs
a clean app through every check to prove none fires on it — the pattern of mPOS's ``ci/check_foreign_apps.py``.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lint_engine_patch  # noqa: E402
import lint_outbound  # noqa: E402
import lint_required_apps  # noqa: E402

PLATFORM_NAMES_FILE = HERE / "platform_doctypes.txt"
MONEY_DOCTYPES = {"POS Invoice", "Sales Invoice", "Sales Order", "Quotation", "Delivery Note", "Payment Entry",
                  "Journal Entry", "POS Closing Entry", "Pricing Rule", "Item Price", "Promotion Bonus Buys Master",
                  "Coupon", "Loyalty Point Entry", "*"}
SALES_DOCTYPES = {"POS Invoice", "Sales Invoice", "Sales Order", "Quotation", "Delivery Note"}
CHANNEL_EVENTS = ("set_missing_values", "calculate_taxes_and_totals")
OVERRIDE_HOOKS = ("override_doctype_class", "extend_doctype_class", "override_whitelisted_methods", "regional_overrides")
THROW_ROOTS = ("frappe", "ivendframework")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "dist", "build"}


class App:
    def __init__(self, path: str, prefix: str | None = None):
        root = pathlib.Path(path).resolve()
        hooks = root / "hooks.py" if (root / "hooks.py").exists() else None
        if hooks is None:
            cands = sorted(p for p in root.glob("*/hooks.py") if p.parent.name not in SKIP_DIRS)
            hooks = cands[0] if cands else None
        if hooks is None:
            raise SystemExit(f"selfcheck: no hooks.py in {root} or one level below — is this an app folder?")
        self.pkg = hooks.parent
        self.root = root if root != self.pkg else self.pkg
        self.hooks_src = hooks.read_text(encoding="utf-8")
        self.hooks = _literal_assigns(self.hooks_src)
        self.name = self.hooks.get("app_name") or self.pkg.name
        self.prefix = prefix or self.name.replace("_", " ")
        self.py: dict[str, str] = {}      # dotted module -> source
        self.py_rel: dict[str, str] = {}  # dotted module -> path relative to the package's parent
        for p in sorted(self.pkg.rglob("*.py")):
            if set(p.relative_to(self.pkg).parts) & SKIP_DIRS:
                continue
            rel = p.relative_to(self.pkg.parent)
            mod = ".".join(rel.with_suffix("").parts)
            mod = mod[: -len(".__init__")] if mod.endswith(".__init__") else mod
            self.py[mod] = p.read_text(encoding="utf-8", errors="replace")
            self.py_rel[mod] = rel.as_posix()

    def shipped(self):
        """(module, path, source) for the code that ships — tests are a test seam, out of scope (as the source lints)."""
        for mod, src in self.py.items():
            if ".tests" in "." + mod or mod.split(".")[-1].startswith("test_"):
                continue
            yield mod, self.py_rel[mod], src


def _literal_assigns(src: str) -> dict:
    """Module-level ``name = <literal>`` in hooks.py. A commented-out line is not code: the AST never sees it."""
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                out[node.targets[0].id] = "<computed>"
    return out


def _as_list(v) -> list:
    return v if isinstance(v, (list, tuple)) else ([v] if v else [])


def _doc_events(app: App) -> dict:
    de = app.hooks.get("doc_events")
    return de if isinstance(de, dict) else {}


# ── the checks: each returns (status, [findings]) ────────────────────────────

def c_required_apps(app: App):
    imported = set()
    for _, _, src in app.shipped():
        for root in _import_roots(src):
            if root in lint_required_apps.PLATFORM_APPS:
                imported.add(root)
    return lint_required_apps.check(app.hooks_src, imported, app.name)


def _import_roots(src: str) -> set[str]:
    out = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


def c_framework_alias(app: App):
    hits = [rel for mod, rel in app.py_rel.items() if "ivendframework" in _import_roots(app.py[mod])]
    if hits:
        return "FAIL", [f"{len(hits)} file(s) import the framework under its alias `ivendframework` — import `frappe`, "
                        f"the published name: " + ", ".join(sorted(hits)[:6]) + (" …" if len(hits) > 6 else "")]
    return "PASS", []


def c_engine_patches(app: App):
    found = []
    for _, rel, src in app.shipped():
        found += lint_engine_patch.find_patches(src, rel)
    return ("FAIL", found) if found else ("PASS", [])


def c_outbound(app: App):
    found = []
    for _, rel, src in app.shipped():
        found += [(rel, k, line, what) for k, line, what in lint_outbound.scan_source(src, rel)]
    hosts = app.hooks.get("partner_outbound_hosts")
    status, lines = lint_outbound.verdict(found, hosts if isinstance(hosts, list) else None)
    return _unread(app, status, lines, ("partner_outbound_hosts",), OUTBOUND_KEPT)


def c_overrides(app: App):
    found = [f"hooks.py sets `{k}` = {_shown(app.hooks[k])}: it replaces or extends platform code for every shop on the "
             f"site (the last app installed wins, and it never runs on the till)" for k in OVERRIDE_HOOKS if app.hooks.get(k)]
    return _unread(app, "FAIL" if found else "PASS", found, [k for k in OVERRIDE_HOOKS if not app.hooks.get(k)],
                   RULE2_KEPT)


# --- scripts of yours inside the shop's site (rules 3 and 4) ---
# Rule 3: inside a customer's site you ship data, not code (a Server Script is code). Rule 4: never your JavaScript
# inside our screens, Desk or the till (a Client Script, a form script hooked in, or a .js beside your own record type).
# The kit already says intake refuses web pages, web templates, custom HTML blocks and script print formats (guide
# chapter 7, recipes/hosted_sandbox.md); the self-check refuses the same records.
# STATED BOUND: other places that can carry a script are not read here, and the person who reviews the app reads them:
# a page's or a report's own .js, a Script Report, a Letter Head's or a dashboard chart source's script, `.html` templates
# beside a record type, `standard_navbar_items`, `web_include_js` and `webform_include_js` (the public website), a script
# the app's own Python inserts at install (a hook imported, set on an attribute, or set through `globals()`, `setattr`
# or `exec` is REVIEW).

SERVER_SCRIPT = ("your code running inside the shop's site (rule 3: inside a customer's site you ship data, not code). "
                 "Instead: a till key, a manifest or a sandboxed function inside the site, or an outside app on your "
                 "own server")
DESK_SCRIPT = ("your JavaScript running in every Desk user's browser, administrators included (rule 4: your screens come "
               "through our doors; never your JavaScript inside our screens). Instead: a declared button, a Desk "
               "action, or your page inside our frame")
PARTNER_MARKUP = ("partner markup or script placed on the shop's own pages (the kit's manifest checker refuses it too). "
                  "Instead: native screens, declared buttons, or your page inside our frame")
SCRIPT_RECORDS = {"Server Script": SERVER_SCRIPT, "Client Script": DESK_SCRIPT, "Custom Script": DESK_SCRIPT,
                  "Web Page": PARTNER_MARKUP, "Web Template": PARTNER_MARKUP, "Custom HTML Block": PARTNER_MARKUP,
                  "Print Format (JS)": PARTNER_MARKUP}
MODULE_RECORD_FOLDERS = ("server_script", "client_script", "web_page", "web_template")
DESK_JS_HOOKS = ("doctype_js", "doctype_list_js", "doctype_tree_js", "doctype_calendar_js", "page_js", "app_include_js")


def _hooks_not_read(app: App, watched=DESK_JS_HOOKS + ("fixtures",)) -> dict[str, int]:
    """Watched hooks that hooks.py handles in a way ``_literal_assigns`` cannot read, each with the first line doing it:
    a sum, ``+=``, ``.append``, ``x[k] = …``, a chained or conditional assignment, a value built from a name
    (``{**COMMON, …}``), an import, an attribute write (``sys.modules[__name__].doc_events = …``), or ``globals()`` /
    ``vars()`` / ``setattr`` / ``exec`` (any watched hook). Any other
    use of the name counts too: it errs towards a person looking. A forbidden script or money hook could hide there."""
    try:
        tree = ast.parse(app.hooks_src)
    except SyntaxError:
        return {}
    plain = {id(t) for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 for t in n.targets}
    out: dict[str, int] = {}
    for n in ast.walk(tree):
        keys = []
        if isinstance(n, ast.Name) and n.id in watched and id(n) not in plain:
            keys = [n.id]
        elif isinstance(n, ast.Attribute) and n.attr in watched:
            keys = [n.attr]
        elif isinstance(n, ast.ImportFrom):
            got = {a.asname or a.name for a in n.names}
            keys = list(watched) if "*" in got else [k for k in watched if k in got]
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("globals", "vars", "setattr",
                                                                                       "exec", "locals"):
            keys = list(watched)
        for k in keys:
            out[k] = min(out.get(k, n.lineno), n.lineno)
    last = {n.targets[0].id: n.lineno for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)}   # the plain assignment ``_literal_assigns`` kept
    for k, line in last.items():
        if k in watched and app.hooks.get(k) == "<computed>":
            out[k] = min(out.get(k, line), line)
    return dict(sorted(out.items()))


RULE1_KEPT = "rule 1 is kept (money enters the sale visibly, before payment)"
RULE2_KEPT = "rule 2 is kept (don't override or patch iVendNext)"
OUTBOUND_KEPT = "every host the app calls is declared (a line above judges only what it could read of the list)"


def _unread(app: App, status: str, findings: list, keys, kept: str):
    """A check that reads a hook the reader could not evaluate never PASSes: each such hook is a REVIEW line. A FAIL
    stays a FAIL."""
    notes = [f"hooks.py:{line}: the self-check could not read `{k}` (built from a name, changed or used after it is "
             f"set, set in a block, or imported), so it cannot tell whether {kept} — a person reviews it"
             for k, line in _hooks_not_read(app, tuple(keys)).items()]
    return ("FAIL" if status == "FAIL" else "REVIEW" if notes or status == "REVIEW" else "PASS"), findings + notes


def _shown(v) -> str:
    return "a value the check cannot read" if v == "<computed>" else repr(v)


def _record_kind(r) -> str | None:
    """What a fixture record is: its doctype, or "Print Format (JS)" for a print format that is a script."""
    kind = r.get("doctype") if isinstance(r, dict) else None
    if kind == "Print Format" and r.get("print_format_type") == "JS":
        return "Print Format (JS)"
    return kind if isinstance(kind, str) else None


def c_site_scripts(app: App):
    fails = []
    for e in _as_list(app.hooks.get("fixtures")):
        dt = e if isinstance(e, str) else (e.get("doctype") or e.get("dt")) if isinstance(e, dict) else None
        if isinstance(dt, str) and dt in SCRIPT_RECORDS:
            fails.append(f"hooks.py fixtures names {dt!r}: that record is {SCRIPT_RECORDS[dt]}")
    # the shop installs every .json under fixtures/, and every <module>/<kind>/<name>/<name>.json for the kinds above;
    # a file holds one record or a list of them, and each record says what it is
    files = {p for p in (app.pkg / "fixtures").rglob("*.json")}
    files |= {p for k in MODULE_RECORD_FOLDERS for p in app.pkg.rglob(f"{k}/*/*.json")}
    for f in sorted(p for p in files if p.is_file()):
        if set(f.relative_to(app.pkg).parts) & SKIP_DIRS:
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        kinds = {_record_kind(r) for r in (rows if isinstance(rows, list) else [rows])}
        for dt in sorted(k for k in kinds if k in SCRIPT_RECORDS):
            fails.append(f"{f.relative_to(app.pkg).as_posix()} holds {dt!r} records: that is {SCRIPT_RECORDS[dt]}")
    for name in DESK_JS_HOOKS:
        v = app.hooks.get(name)
        for key, files in (v.items() if isinstance(v, dict) else [(None, v)]):
            if files and files != "<computed>":
                at = f"{name}[{key!r}]" if key else name
                fails.append(f"hooks.py {at} -> {', '.join(map(str, _as_list(files)))}: that is {DESK_SCRIPT}")
    # the form loads <name>.js, <name>_list|_tree|_calendar.js and regional/<country>[_list].js beside <name>.json by itself
    for f in sorted(set(app.pkg.rglob("doctype/*/*.js")) | set(app.pkg.rglob("doctype/*/regional/*.js"))):
        if not f.is_file():
            continue
        d = f.parent.parent if f.parent.name == "regional" else f.parent
        loaded = f.parent.name == "regional" or f.stem in {d.name + sfx for sfx in ("", "_list", "_tree", "_calendar")}
        code = "".join(_strip_js_comments(f.read_text(encoding="utf-8", errors="replace"))).strip()
        if loaded and code and (d / f"{d.name}.json").exists() and not set(f.relative_to(app.pkg).parts) & SKIP_DIRS:
            fails.append(f"{f.relative_to(app.pkg.parent).as_posix()}: a script beside your record type loads into "
                         f"its Desk form: that is {DESK_SCRIPT}")
    reviews = [f"hooks.py:{line} sets `{n}` in a way the check cannot read — it could carry a script (rules 3 and 4), "
               f"so a reviewer reads it" for n, line in _hooks_not_read(app).items()]
    return ("FAIL" if fails else "REVIEW" if reviews else "PASS"), fails + reviews


def c_channel_hook(app: App):
    found = [f"doc_events[{dt!r}][{ev!r}] -> {h}: runs when the till composes a sale and NOT on a Desk or API sale, "
             f"so the same sale gets a different answer by channel" for dt, evs in _doc_events(app).items()
             if isinstance(evs, dict) for ev, h in evs.items() if ev in CHANNEL_EVENTS]
    return _unread(app, "FAIL" if found else "PASS", found, ("doc_events",), RULE1_KEPT)


def c_money_validate(app: App):
    found = [f"doc_events[{dt!r}][{ev!r}] -> {h}: a check on a money record — a second reviewer reads it"
             for dt, evs in _doc_events(app).items() if dt in MONEY_DOCTYPES and isinstance(evs, dict)
             for ev, h in evs.items() if ev in ("validate", "before_validate")]
    return _unread(app, "REVIEW" if found else "PASS", found, ("doc_events",), RULE1_KEPT)


# --- the call graph: what a document event reaches inside the app (Trap 2, Trap 5) ---
# STATED BOUND (review fold R1): the walk follows module-level functions reached by name, by an imported name, by an
# imported module's attribute and by a relative import. It does NOT follow class methods (`self.helper()`), handlers
# bound at run time (`h = A().run`); a handler or callee it cannot resolve, and a `doc_events` hooks.py sets in a way
# the reader cannot evaluate, are REVIEW, never a silent pass.

SAVE_PATH_EVENTS = ("before_validate", "validate", "before_save", "before_insert", "before_submit", "on_submit",
                    "on_update")
SUBMIT_DOCTYPES = ("POS Invoice", "Sales Invoice", "*")   # a till sale is merged into its own Sales Invoice at close
MONEY_ATTR_RE = re.compile(r"^(?:" + "rate|price_list_rate|net_rate|discount_amount|additional_discount_percentage|"
                           "discount_percentage|amount|net_amount|total|net_total|grand_total|rounded_total|"
                           "paid_amount|outstanding_amount|base_[a-z_]+|[a-z_]+_amount|[a-z_]+_total" + r")$")
RETOTAL_CALLS = ("calculate_taxes_and_totals", "set_missing_values", "apply_pricing_rule")


def _bindings(tree: ast.AST, mod: str, is_pkg: bool) -> tuple[dict, set[str], set[str]]:
    """(name -> dotted target) for imports, relative ones resolved against ``mod``; names bound to a throw function;
    aliases bound to the framework module under either of its names."""
    names, throw_names, throw_roots = {}, set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                bound = a.asname or a.name.split(".")[0]
                names[bound] = a.name if a.asname else a.name.split(".")[0]
                if a.name in THROW_ROOTS:
                    throw_roots.add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom):
            base = n.module
            if n.level:
                pkg = mod if is_pkg else mod.rsplit(".", 1)[0]
                for _ in range(n.level - 1):
                    pkg = pkg.rsplit(".", 1)[0]
                base = pkg + (f".{n.module}" if n.module else "")
            if not base:
                continue
            for a in n.names:
                names[a.asname or a.name] = f"{base}.{a.name}"
                if base in THROW_ROOTS and a.name in ("throw", "msgprint"):
                    throw_names.add(a.asname or a.name)
    return names, throw_names, throw_roots


def _defs(app: App) -> dict:
    """dotted function path -> (FunctionDef, module, bindings) for every top-level function in the app."""
    out = {}
    for mod, src in app.py.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        b = _bindings(tree, mod, app.py_rel[mod].endswith("__init__.py"))
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[f"{mod}.{n.name}"] = (n, mod, b)
    return out


def _scan_fn(fn: ast.AST, mod: str, b: tuple, is_pkg: bool = False) -> dict:
    names, tnames, troots = b
    ln, lt, lr = _bindings(fn, mod, is_pkg)     # function-local imports count too (the alias is often imported inline)
    names, tnames, troots = {**names, **ln}, tnames | lt, troots | lr
    out = {"throws": [], "raises": [], "money": [], "callees": []}
    for n in ast.walk(fn):
        if isinstance(n, ast.Raise):
            out["raises"].append(n.lineno)
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                field = t.attr if isinstance(t, ast.Attribute) else (
                    t.slice.value if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and isinstance(t.slice.value, str) else None)
                if field and MONEY_ATTR_RE.match(field):
                    out["money"].append((n.lineno, f"writes `{field}`"))
        elif isinstance(n, ast.Call):
            f = n.func
            raising_msgprint = any(k.arg == "raise_exception" and not (isinstance(k.value, ast.Constant)
                                                                     and not k.value.value) for k in n.keywords)
            if isinstance(f, ast.Name):
                is_msgprint = names.get(f.id, "").endswith("msgprint")
                if f.id in tnames and (not is_msgprint or raising_msgprint):
                    out["throws"].append(n.lineno)
                else:
                    out["callees"].append(names.get(f.id, f"{mod}.{f.id}"))
            elif isinstance(f, ast.Attribute):
                base = lint_outbound._dotted(f.value)
                if base in troots and (f.attr == "throw" or (f.attr == "msgprint" and raising_msgprint)):
                    out["throws"].append(n.lineno)
                elif f.attr in RETOTAL_CALLS or (f.attr == "run_method" and n.args and isinstance(n.args[0], ast.Constant)
                                                 and n.args[0].value in RETOTAL_CALLS):
                    out["money"].append((n.lineno, f"re-prices or re-totals the document (`{f.attr}`)"))
                elif f.attr in ("set", "db_set") and n.args and isinstance(n.args[0], ast.Constant) and \
                        isinstance(n.args[0].value, str) and MONEY_ATTR_RE.match(n.args[0].value):
                    out["money"].append((n.lineno, f"sets `{n.args[0].value}`"))
                elif base and base.split(".")[0] in names:
                    head = base.split(".")[0]
                    out["callees"].append(names[head] + base[len(head):] + "." + f.attr)
    return out


def _reach(app: App, defs: dict, handler: str):
    """Yield (chain, module, scan) for every app function the handler reaches; ("unresolved", path) for a handler the
    walk cannot find inside the app."""
    if handler not in defs:
        yield "unresolved", handler, None
        return
    seen, queue = set(), [(handler, [handler])]
    while queue:
        path, chain = queue.pop(0)
        if path in seen or path not in defs:
            continue
        seen.add(path)
        fn, mod, b = defs[path]
        scan = _scan_fn(fn, mod, b, app.py_rel[mod].endswith("__init__.py"))
        yield chain, mod, scan
        for c in scan["callees"]:
            if c in defs:
                queue.append((c, chain + [c.rsplit(".", 1)[-1]]))


def _handlers(app: App, doctypes, events):
    de = _doc_events(app)
    for dt in doctypes:
        evs = de.get(dt)
        if not isinstance(evs, dict):
            continue
        for ev, val in evs.items():
            if ev in events:
                for h in _as_list(val):
                    yield dt, ev, h


def c_throw_at_submit(app: App):
    defs, fails, reviews = _defs(app), [], []
    for dt, ev, handler in _handlers(app, SUBMIT_DOCTYPES, SAVE_PATH_EVENTS):
        for chain, mod, scan in _reach(app, defs, handler):
            if chain == "unresolved":
                if handler.split(".")[0] == app.name:
                    reviews.append(f"{dt} {ev} -> {handler}: the walk cannot find this handler — a reviewer reads it")
                continue
            for line in scan["throws"]:
                fails.append(f"{dt} {ev} -> {' -> '.join(chain)}: a refusal at {app.py_rel[mod]}:{line} rejects the "
                             f"sale — an offline sale replayed later was already paid for")
            for line in scan["raises"]:
                reviews.append(f"{dt} {ev} -> {' -> '.join(chain)}: a `raise` at {app.py_rel[mod]}:{line} — a "
                               f"reviewer checks it can never reach the sale")
    return _unread(app, "FAIL" if fails else "REVIEW" if reviews else "PASS", sorted(set(fails)) + sorted(set(reviews)),
                   ("doc_events",), RULE1_KEPT)


def c_server_money(app: App):
    """Trap 5, on the server: a hook on a money record that writes a rate, an amount or a total, or re-prices the
    document. The till's preview never runs a save hook, so the customer pays one figure and the books show another."""
    defs, fails = _defs(app), []
    for dt, ev, handler in _handlers(app, sorted(MONEY_DOCTYPES), set(SAVE_PATH_EVENTS) | {
            "on_cancel", "before_cancel", "on_update_after_submit", "before_update_after_submit", "on_change"}):
        for chain, mod, scan in _reach(app, defs, handler):
            if chain == "unresolved":
                continue
            for line, what in scan["money"]:
                fails.append(f"{dt} {ev} -> {' -> '.join(chain)}: {app.py_rel[mod]}:{line} {what} — money the till "
                             f"never showed the customer")
    return _unread(app, "FAIL" if fails else "PASS", sorted(set(fails)), ("doc_events",), RULE1_KEPT)


# --- browser-side money ---

MONEY_FIELDS = (r"discount_amount|additional_discount_percentage|discount_percentage|price_list_rate|net_rate|rate|"
                r"amount|net_amount|grand_total|rounded_total|paid_amount|base_[a-z_]+|[a-z_]+_amount")
JS_SET_RE = re.compile(r"""set_value\s*\(\s*(?:[^,()]+,\s*){0,2}["'](""" + MONEY_FIELDS + r""")["']""")
JS_ASSIGN_RE = re.compile(r"""(?:\.(""" + MONEY_FIELDS + r""")|\[\s*["'](""" + MONEY_FIELDS +
                          r""")["']\s*\])\s*(?:[-+*/]=|=(?!=))""")
JS_IMPORT_RE = re.compile(r"""import\s+(?:[^'"]*?from\s+)?["'](\.{1,2}/[^"']+)["']""")


def _strip_js_comments(src: str) -> list[str]:
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    out = []
    for line in src.split("\n"):
        out.append("" if line.lstrip().startswith("//") else re.sub(r"(?<![:\"'\\])//.*$", "", line))
    return out


def _resolve_js(app: App, value: str) -> list[pathlib.Path]:
    v = value.strip()
    if v.startswith(f"/assets/{app.name}/"):
        cands = [app.pkg / "public" / v[len(f"/assets/{app.name}/"):]]
    elif v.endswith(".bundle.js") and "/" not in v:
        cands = list((app.pkg / "public").rglob(v))
    else:
        cands = [app.pkg / v]
    return [c for c in cands if c.exists()]


def _js_closure(app: App, files: list[pathlib.Path]) -> list[pathlib.Path]:
    seen, queue = [], list(files)
    while queue:
        f = queue.pop(0)
        if f in seen or not f.exists():
            continue
        seen.append(f)
        for rel in JS_IMPORT_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
            nxt = (f.parent / rel).resolve()
            queue += [nxt] if nxt.suffix else [nxt.with_suffix(".js")]
    return seen


def c_browser_money(app: App):
    targets: list[tuple[str, pathlib.Path]] = []
    missing = []
    dj = app.hooks.get("doctype_js") if isinstance(app.hooks.get("doctype_js"), dict) else {}
    wanted = [(f"doctype_js[{dt!r}]", v) for dt, val in dj.items() if dt in SALES_DOCTYPES for v in _as_list(val)]
    wanted += [("app_include_js", v) for v in _as_list(app.hooks.get("app_include_js"))]
    for why, v in wanted:
        got = _resolve_js(app, v)
        targets += [(why, p) for p in got]
        if not got:
            missing.append(f"{why} -> {v}: the check cannot find this script — a reviewer reads it")
    found = []
    for why, start in targets:
        for f in _js_closure(app, [start]):
            # the WHOLE text, not line by line: a call is often split as `frm.set_value(\n  "field", …)`
            text = "\n".join(_strip_js_comments(f.read_text(encoding="utf-8", errors="replace")))
            for rx in (JS_SET_RE, JS_ASSIGN_RE):
                for m in rx.finditer(text):
                    field, line = next(g for g in m.groups() if g), text.count("\n", 0, m.start()) + 1
                    found.append(f"{why} -> {f.relative_to(app.pkg.parent).as_posix()}:{line} writes `{field}` in "
                                 f"the browser: money set on a screen bypasses the server's pricing and never reaches "
                                 f"the till")
    return ("FAIL" if found else "REVIEW" if missing else "PASS"), sorted(set(found)) + missing


# --- names ---

def _platform_names() -> set[str]:
    return {ln.strip() for ln in PLATFORM_NAMES_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def c_names(app: App):
    pre = app.prefix.upper()
    ok = lambda n: n.upper() == pre or n.upper().startswith(pre + " ")  # noqa: E731
    platform = _platform_names()
    doctypes = []
    for j in app.pkg.rglob("doctype/*/*.json"):
        if j.stem == j.parent.name:
            try:
                d = json.loads(j.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("doctype") == "DocType" and d.get("name"):
                doctypes.append(d["name"])
    modules = [m.strip() for m in (app.pkg / "modules.txt").read_text(encoding="utf-8").splitlines()
               if m.strip()] if (app.pkg / "modules.txt").exists() else []
    fails = [f"record type {n!r} has the same name as the platform's own — one of the two cannot be installed or "
             f"removed cleanly" for n in sorted(set(doctypes) & platform)]
    bad_dt = sorted(n for n in doctypes if not ok(n))
    if bad_dt:
        fails.append(f"{len(bad_dt)} record type(s) without the app's prefix {app.prefix!r}: "
                     + ", ".join(bad_dt[:8]) + (" …" if len(bad_dt) > 8 else ""))
    fails += [f"module {m!r} without the prefix {app.prefix!r}" for m in modules if not ok(m)]
    fprefix = app.prefix.lower().replace(" ", "_") + "_"
    own = set(doctypes)
    bad = sorted({f"{r.get('dt')}.{r.get('fieldname')} ({f.relative_to(app.pkg).as_posix()})"
                  for f, r in _custom_fields(app, modules)
                  if r.get("dt") not in own and not str(r.get("fieldname", "")).startswith(fprefix)})
    if bad:
        fails.append(f"{len(bad)} field(s) added to others' record types without the prefix {fprefix!r}: "
                     + ", ".join(bad[:8]) + (" …" if len(bad) > 8 else ""))
    return ("FAIL", fails) if fails else ("PASS", [])


def _custom_fields(app: App, modules: list[str]):
    """(file, record) for every Custom Field the shop installs from the app, from the three places it reads them: a
    fixture file of any name (the top of ``fixtures/``), a module's own record (<module>/custom_field/<name>/<name>.json)
    and a module's customisations (<module>/custom/<doctype>.json, its `custom_fields` list). A file holds one record or
    a list. The modules are those of modules.txt. Not read: a field the app's own Python creates at install."""
    mods = [m.replace(" ", "_").replace("-", "_").lower() for m in modules]
    custom = {f for m in mods for f in app.pkg.glob(f"{m}/custom/*.json")}
    files = set((app.pkg / "fixtures").glob("*.json")) | custom
    files |= {f for m in mods for f in app.pkg.glob(f"{m}/custom_field/*/*.json")}
    for f in sorted(files):
        if not f.is_file() or set(f.relative_to(app.pkg).parts) & SKIP_DIRS:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rows = data.get("custom_fields") if f in custom and isinstance(data, dict) else data
        for r in rows if isinstance(rows, list) else [rows]:
            if isinstance(r, dict) and (f in custom or r.get("doctype") == "Custom Field"):
                yield f, r


# --- guest endpoints, SQL writes ---

def _whitelist_guest(fn: ast.AST) -> bool:
    for d in getattr(fn, "decorator_list", []):
        if isinstance(d, ast.Call) and lint_outbound._dotted(d.func).endswith("whitelist"):
            for kw in d.keywords:
                if kw.arg == "allow_guest" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    return True
    return False


def c_guest(app: App):
    declared = set(_as_list(app.hooks.get("partner_guest_methods")))
    found = []
    for mod, rel, src in app.shipped():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _whitelist_guest(n):
                if f"{mod}.{n.name}" not in declared:
                    found.append(f"{rel}:{n.lineno} `{n.name}` is open to anyone without signing in "
                                 f"(allow_guest=True) and is not declared in partner_guest_methods")
    return ("FAIL", found) if found else ("PASS", [])


SQL_WRITE_RE = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(insert|update|delete|replace|drop|alter|truncate|create|rename|"
                          r"grant)\b", re.I)


def c_sql_writes(app: App):
    fails, reviews = [], []
    for _, rel, src in app.shipped():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            dotted = lint_outbound._dotted(n.func)
            if dotted.endswith("db.sql_ddl"):
                fails.append(f"{rel}:{n.lineno} raw schema change (db.sql_ddl)")
            elif dotted.endswith("db.sql") and n.args:
                a = n.args[0]
                text = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else \
                    "".join(v.value for v in a.values if isinstance(v, ast.Constant)) if isinstance(a, ast.JoinedStr) \
                    else None
                if text is None:
                    reviews.append(f"{rel}:{n.lineno} db.sql with a query built at run time — a reviewer reads it")
                elif SQL_WRITE_RE.match(text):
                    fails.append(f"{rel}:{n.lineno} a raw SQL write ({SQL_WRITE_RE.match(text).group(1).upper()}): "
                                 f"it skips validation, permissions and the audit trail — save documents instead")
    return ("FAIL" if fails else "REVIEW" if reviews else "PASS"), fails + reviews


# --- secrets, licence ---

SECRET_RES = [
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("a Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}")),
    ("a live payment key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("a hard-coded secret", re.compile(r"""(?i)\b(?:api[_-]?key|api[_-]?secret|client[_-]?secret|secret[_-]?key|"""
                                       r"""password|passwd|auth[_-]?token|access[_-]?token)\b["']?\s*[:=]\s*["']"""
                                       r"""([^"'\s]{12,})["']""")),
]
PLACEHOLDER_RE = re.compile(r"(?i)example|xxxx|changeme|your[_-]|dummy|placeholder|<|\$\{|\*\*\*|redacted|test")
TEXT_SUFFIXES = {".py", ".js", ".json", ".txt", ".md", ".html", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".env",
                 ".csv", ".vue", ".ts", ".css", ".scss", ""}


def c_secrets(app: App):
    found = []
    for p in sorted(app.root.rglob("*")):
        if not p.is_file() or set(p.relative_to(app.root).parts) & SKIP_DIRS or p.suffix not in TEXT_SUFFIXES:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for label, rx in SECRET_RES:
                m = rx.search(line)
                if m and not (m.groups() and PLACEHOLDER_RE.search(m.group(1))):
                    found.append(f"{p.relative_to(app.root).as_posix()}:{i} looks like {label} (value not shown)")
    return ("FAIL", found) if found else ("PASS", [])


LICENCE_TEMPLATE_RE = re.compile(r"(?i)<year>|\[year\]|\[yyyy\]|<copyright holders?>|\[fullname\]|"
                                 r"\[name of copyright owner\]|your name|<name of author>|\{\{\s*year\s*\}\}")


def c_licence(app: App):
    files = [p for p in app.root.iterdir() if p.is_file() and p.name.lower().startswith(("license", "licence"))]
    for p in files:
        if LICENCE_TEMPLATE_RE.search(p.read_text(encoding="utf-8", errors="replace")):
            return "REVIEW", [f"{p.name} still carries a template placeholder — fill in the year and the holder"]
    if not files and not app.hooks.get("app_license"):
        return "REVIEW", ["no licence file and no app_license in hooks.py — say under what terms the shop runs it"]
    return "PASS", []


CHECKS = [
    ("required_apps", "dependencies declared in required_apps (copy of mPOS check_foreign_apps)", c_required_apps),
    ("framework_alias", "no import of the framework's alias", c_framework_alias),
    ("runtime_patches", "no run-time patching of platform code (copy of mPOS check_engine_attr_patch_allowlist)",
     c_engine_patches),
    ("outbound", "no outbound call except to declared hosts (copy of Integration Core check_no_outbound_calls)",
     c_outbound),
    ("overrides", "no class, endpoint or regional override", c_overrides),
    ("site_scripts", "no script of yours inside the shop's site (rules 3 and 4)", c_site_scripts),
    ("channel_hook", "no hook on the till's sale composition", c_channel_hook),
    ("money_validate", "checks on money records get a second reviewer", c_money_validate),
    ("throw_at_submit", "nothing reachable from a till sale's save or submit can refuse it", c_throw_at_submit),
    ("server_money", "no hook on a money record changes a rate, an amount or a total", c_server_money),
    ("browser_money", "no money written in the browser", c_browser_money),
    ("names", "names carry the app's prefix and clash with nothing in the platform", c_names),
    ("guest", "every endpoint open without sign-in is declared", c_guest),
    ("sql_writes", "no raw SQL writes", c_sql_writes),
    ("secrets", "no secret in the source", c_secrets),
    ("licence", "a filled-in licence", c_licence),
]


def run(path: str, prefix: str | None = None, manifest: str | None = None) -> dict:
    app = App(path, prefix)
    results = []
    for cid, title, fn in CHECKS:
        status, findings = fn(app)
        results.append({"id": cid, "title": title, "status": status, "findings": findings})
    if manifest:
        sys.path.insert(0, str(HERE.parent / "manifest"))
        import validate as manifest_validate  # noqa: E402  (the manifest checker, unchanged)
        import site_rules  # noqa: E402  (what the shop's install refuses after the checker)
        m = json.loads(pathlib.Path(manifest).read_text(encoding="utf-8"))
        refusals = manifest_validate.validate(m) or site_rules.refusals(m)
        results.append({"id": "manifest", "title": "the manifest passes the manifest validator", "status":
                        "FAIL" if refusals else "PASS",
                        "findings": [f"{r.get('where')}: {r.get('reason')}" for r in refusals]})
    return {"app": app.name, "prefix": app.prefix, "path": str(app.root), "results": results,
            "verdict": "FAIL" if any(r["status"] == "FAIL" for r in results) else
                       "REVIEW" if any(r["status"] == "REVIEW" for r in results) else "PASS"}


def report(out: dict) -> str:
    lines = [f"selfcheck {out['app']} (prefix {out['prefix']!r}) — {out['path']}"]
    for r in out["results"]:
        lines.append(f"  {r['status']:6s} {r['id']:16s} {r['title']}")
        for f in r["findings"][:12]:
            lines.append(f"           - {f}")
        if len(r["findings"]) > 12:
            lines.append(f"           … and {len(r['findings']) - 12} more")
    lines.append(f"VERDICT {out['verdict']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        import selftest
        return selftest.main()
    args, opts = [], {}
    it = iter(argv)
    for a in it:
        if a in ("--prefix", "--manifest", "--json"):
            opts[a[2:]] = next(it, None)
        else:
            args.append(a)
    if len(args) != 1:
        print(__doc__)
        return 2
    out = run(args[0], opts.get("prefix"), opts.get("manifest"))
    print(report(out))
    if opts.get("json"):
        pathlib.Path(opts["json"]).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 1 if out["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
