"""site/devmap.py — the developer's map ("What you can use", site/pages/map.md) and the record-type pages, each written
from the kit file that already defines it, so neither can drift from its source. Read by site/build.py.

    {{map: calls}}     part (a): api/openapi.yaml's record calls, api/README.md's method names (a line each from
                       site/map.json), the event feed and the other calls an app makes
    {{map: points}}    part (b): one row per page of contracts/pages/, in two tables (called on your service; declared, not
                       called); each cell is a quote of its page (site/map.json "points"), held to the page
    {{map: manifest}}  part (c): every key of the manifest schema's $defs.manifest.properties, each with a sample that uses it
    {{map: screens}}   part (d): the screens you can add, each with a screenshot from a sample
    record pages       api/records/*.json (tools/records/records.py fetch): records/index.html and one page per record type

`errors()` is the build's check of all of it: a method name, a contract page, a manifest key, a record type of the API
description or a quoted sentence that leaves its source while the map keeps it (or arrives while the map lacks it) fails the
build; site/test_site.py plants a fault in each and watches it fail. Bound, stated: the hand-written lines (a method's one
line, a manifest key's words, a record type's first paragraph) are held by review, not by the build; a quote is held to its
page, not to its section; a cell marked "none" is not re-read.
"""
from __future__ import annotations

import json
import pathlib
import posixpath
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "map.json"
SPEC = "api/openapi.yaml"
README = "api/README.md"
SCHEMA = "contracts/extension_contracts/package_manifest.v1.schema.json"
POINTS = "contracts/pages"
RECORDS = "api/records"
MAP_SRC = "site/pages/map.md"
METHOD = "/api/method/ivendnext_mpos.api.v1."
TYPE_IN_PATH = re.compile(r"^/api/(?:resource|v2/document)/([^/{]+)")


def data(path: pathlib.Path = DATA) -> dict:
    return json.loads(path.read_text("utf-8"))


def cell(s) -> str:
    return " ".join(str(s or "").split()).replace("|", "\\|")


def squash(s: str) -> str:
    return " ".join(str(s).split())


def rel(target: str, src: str = MAP_SRC) -> str:
    return posixpath.relpath(target, posixpath.dirname(src))


# ── part (a): the calls your app makes ─────────────────────────────────────────────────────────────────────────────────
def operations(root: pathlib.Path = ROOT) -> list[tuple[str, str, str]]:
    """(method, path, summary) for every operation of api/openapi.yaml, in its order."""
    import yaml
    spec = yaml.safe_load((root / SPEC).read_text("utf-8"))
    return [(m.upper(), path, (op or {}).get("summary") or "") for path, ops in (spec.get("paths") or {}).items()
            for m, op in (ops or {}).items() if m in ("get", "post", "put", "patch", "delete")]


def methods(root: pathlib.Path = ROOT) -> list[tuple[str, str]]:
    """(name, since) for every name api/README.md's *The names:* list gives, in its order: "since" is the POS build or
    version the list names before it, or "" for the first names."""
    text = (root / README).read_text("utf-8")
    seg = text.split("The names:", 1)[1].split("A call you need", 1)[0] if "The names:" in text else ""
    since, out = "", []
    for m in re.finditer(r"from POS (?:build|version) ([0-9.]+)|`([a-z0-9_]+)`", seg):
        if m.group(1):
            since = m.group(1)
        else:
            out.append((m.group(2), since))
    return out


def record_type_of(path: str) -> str:
    m = TYPE_IN_PATH.match(path)
    return urllib.parse.unquote(m.group(1)).strip() if m else ""


def record_link(name: str, have: set[str], src: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"[{name}](site:records/{slug}.html)" if slug in have else (name or "any record type")


def api_anchor(path: str) -> str:                     # the API reference page's heading id for a path (build.slug of it)
    return re.sub(r"[^\w\- ]", "", path.lower()).replace(" ", "-")


def calls(have: set[str], src: str = MAP_SRC, root: pathlib.Path = ROOT, d: dict | None = None) -> str:
    d = d or data()
    api = rel("site/pages/api.md", src)
    out = ["### Records: read and write any record type", "",
           "Every record call is the same few addresses for every record type, `/api/resource/⟨Record Type⟩`. The calls the "
           f"samples make, each with its parameters and answers on the [API reference]({api}); every record type with its "
           f"fields on its own page ([all record types](site:records/index.html)).", "",
           "| Call | Address | What it does | Record type |", "|---|---|---|---|"]
    for m, path, summary in operations(root):
        out.append(f"| `{m}` | [`{path}`]({api}#{api_anchor(path)}) | {cell(summary)} | {record_link(record_type_of(path), have, src)} |")
    names = methods(root)
    out += ["", "### iVendNext methods", "",
            f"Calls other than records, each `POST` (or `GET` to read) to `{METHOD}⟨name⟩`: the engine's own functions under "
            f"iVendNext names, with the same rights and answers. The list and what to watch for: [`api/README.md`]({rel(README, src)}). "
            "*From* is the first POS build that has the method; *the first list* is every build with the partner API.", "",
            "| Method | From | What it does |", "|---|---|---|"]
    for name, since in names:
        out.append(f"| `{name}` | {('POS ' + since) if since else 'the first list'} | {cell(d['methods'].get(name, ''))} |")
    out += ["", "### The event feed and the other calls your app makes", "",
            "| Address | What it does | More |", "|---|---|---|"]
    for c in d["other_calls"]:
        out.append(f"| `{c['address']}` | {cell(c['what'])} | [details]({c['detail']}) |")
    out += ["", "### Reports and reading many records at once", "",
            f"- **The retailer's own reports:** `run_report` and `prepare_report` above; what to watch for: [reading the retailer's reports]({rel('recipes/shop_reports.md', src)}).",
            f"- **Many records in one call** (sale lines, totals and groups): [read many records at once]({rel('recipes/bulk_reads.md', src)}).",
            f"- **Signing in:** every call carries `Authorization: token ⟨api key⟩:⟨api secret⟩` and runs as your app's own user ([security and the handshake]({rel('site/pages/security.md', src)})).", ""]
    return "\n".join(out)


# ── part (b): the calls iVendNext makes to your service ─────────────────────────────────────────────────────────────────
CALL_COLS = [("when", "When it fires"), ("sends", "What it sends"), ("answer", "What you answer"), ("limit", "Time limit"),
             ("sees", "What the cashier or user sees")]
DECLARED_COLS = [("what", "What you declare"), ("when", "When it applies"), ("sees", "What the cashier or user sees")]


def contract_pages(root: pathlib.Path = ROOT) -> list[str]:
    return sorted(p.stem for p in (root / POINTS).glob("*.md"))


def page_title(stem: str, root: pathlib.Path = ROOT) -> str:
    m = re.search(r"^# (.+)$", (root / POINTS / f"{stem}.md").read_text("utf-8"), re.M)
    return re.sub(r"[`*]", "", m.group(1)).split(" — ")[0].split(" (")[0].strip() if m else stem


def quote(text) -> str:
    """A cell of part (b): the contract's own words in quotation marks, several quotes joined; "none" when it says nothing."""
    if text == "none":
        return "none stated"
    return " … ".join(f"“{cell(t)}”" for t in ([text] if isinstance(text, str) else text))


def pieces(text) -> list:
    return [] if text == "none" else [text] if isinstance(text, str) else list(text)


def points(src: str = MAP_SRC, root: pathlib.Path = ROOT, d: dict | None = None) -> str:
    d = d or data()
    rows = {r["page"]: r for r in d["points"]}
    out = []
    for kind, head, cols, lede in (
            ("calls", "Calls on your service", CALL_COLS,
             "iVendNext calls your service's address over HTTPS, signed with that retailer's secret, at the moment named. "
             "Each cell is the contract page's own words."),
            ("declared", "Declared, not called", DECLARED_COLS,
             "Nothing calls your service at run time. Some you declare as data in your manifest (save rules, field rules, "
             "list marks, register books, a fiscal reader, a sandboxed price module); some are records or settings the "
             "retailer makes in Desk (a scan source, a label layout, the receipt's lines); the print readers are what a print "
             "format may call; and the event feed and the open check are calls your app makes (part a). Each contract page "
             "says which. Each cell is the contract page's own words.")):
        out += [f"### {head}", "", lede, "", "| Extension point | " + " | ".join(c[1] for c in cols) + " |",
                "|---" * (len(cols) + 1) + "|"]
        for stem in contract_pages(root):
            r = rows.get(stem)
            if r and r["table"] == kind:
                link = f"[{page_title(stem, root)}]({rel(f'{POINTS}/{stem}.md', src)})"
                out.append(f"| {link} | " + " | ".join(quote(r.get(k, 'none')) for k, _ in cols) + " |")
        for r in d.get("more_points", []):
            if r["table"] == kind:
                out.append(f"| [{r['name']}]({rel(r['source'], src)}) | " + " | ".join(quote(r.get(k, 'none')) for k, _ in cols) + " |")
        out.append("")
    return "\n".join(out)


# ── part (c): what a manifest can add ───────────────────────────────────────────────────────────────────────────────
def schema_keys(root: pathlib.Path = ROOT) -> list[str]:
    return list(json.loads((root / SCHEMA).read_text("utf-8"))["$defs"]["manifest"]["properties"])


POINT_OF = {"list_marks": "list_mark", "fiscal_readers": "fiscal_reader", "register_books": "register_book",
            "save_rules": "save_rules", "desk_actions": "desk_action", "remote_keys": "remote_till_key"}


def example_of(key: str, root: pathlib.Path = ROOT) -> str:
    """The first sample manifest that uses `key`, else the first accepted contract sample that does, else the first accepted
    sample of the extension point the key declares; "" when none does."""
    for f in sorted(root.glob("samples/*/manifest.json"), key=lambda p: int(re.sub(r"\D", "", p.parent.name.split("_")[0]))) + \
            sorted(root.glob("samples/*/*manifest.json")) + \
            sorted(root.glob("contracts/extension_contracts/samples/package_manifest/accepted/*.json")):
        m = json.loads(f.read_text("utf-8"))
        m = m.get("payload", m)
        if m.get(key) not in (None, [], {}, ""):
            return str(f.relative_to(root))
    point = POINT_OF.get(key)
    found = sorted(root.glob(f"contracts/extension_contracts/samples/{point}/accepted/*.json")) if point else []
    return str(found[0].relative_to(root)) if found else ""


def single_example(root: pathlib.Path = ROOT) -> str:
    for f in sorted(root.glob("samples/*/*manifest.json")) + sorted(root.glob("contracts/extension_contracts/samples/package_manifest/accepted/*.json")):
        m = json.loads(f.read_text("utf-8"))
        m = m.get("payload", m)
        if any(isinstance(t, dict) and t.get("issingle") for t in m.get("doctypes") or []):
            return str(f.relative_to(root))
    return ""


def link_file(path: str, src: str) -> str:
    if not path:
        return "none in the kit yet"
    label = ("sample " + path.split("/")[1].split("_")[0].upper()) if path.startswith("samples/") else "an accepted sample of its contract"
    return f"[{label}]({rel(path, src)})"


def manifest(src: str = MAP_SRC, root: pathlib.Path = ROOT, d: dict | None = None) -> str:
    d = d or data()
    guide = rel("guide/07_manifests.md", src)
    out = [f"Every kind of thing a manifest can install, from the manifest's own schema ([`{posixpath.basename(SCHEMA)}`]({rel(SCHEMA, src)})). "
           f"How to write each: [chapter 7]({guide}) and [the manifest recipe]({rel('recipes/manifest.md', src)}); check yours with "
           "`python3 tools/manifest/validate.py manifest.json`.", "",
           "| You can add | Manifest key | What it is | An example |", "|---|---|---|---|"]
    for key in schema_keys(root):
        if key in d["app_keys"]:
            continue
        label, what = d["manifest"].get(key, ["", ""])
        out.append(f"| {label} | `{key}` | {cell(what)} | {link_file(example_of(key, root), src)} |")
    out.append(f"| Roles | none: name them where they are used | Each role your manifest names (in its record types' permissions, workflows or Desk buttons) that starts with your prefix is made, empty, by the install, and removed at uninstall; the retailer gives it to people. With an event feed the install also makes your app's own user with the role `⟨PREFIX⟩ Integration`. Rights on the retailer's own record types are the retailer's to grant ([chapter 7]({guide}); [the app's user]({rel('recipes/integration_user.md', src)})). | {link_file(example_of('workflows', root), src)} |")
    out.append(f"| Settings | `doctypes`, with `\"issingle\": 1` | One record of your app's settings, no list, edited by the retailer in Desk and read by your service at `/api/resource/⟨type⟩/⟨type⟩` ([chapter 7]({guide})). | {link_file(single_example(root), src)} |")
    out += ["", "The keys that describe the app itself, not something it adds: " + ", ".join(f"`{k}`" for k in d["app_keys"]) + ".", ""]
    return "\n".join(out)


# ── part (d): the screens you can add ───────────────────────────────────────────────────────────────────────────────
def screens(src: str = MAP_SRC, d: dict | None = None) -> str:
    d = d or data()
    out = ["| Where | The screen | What you can show | The door | The recipe | Picture |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(d["screens"], 1):
        out.append(f"| {s['where']} | {s['screen']} | {cell(s['show'])} | {s['door']} | [recipe]({s['recipe']}) | [picture {i}](#picture-{i}) |")
    out += ["", f"Every picture is a screenshot taken on our test bench, of a kit sample unless its caption says otherwise. Find the moment first; the door follows. "
            f"The whole story: [chapter 13a, screens and user experience]({rel('guide/13a_screens_and_ux.md', src)}).", ""]
    for i, s in enumerate(d["screens"], 1):
        out += [f"#### Picture {i}", "", f"![{s['alt']}]({s['shot']})", "",
                f"*{s['where']}, {s['screen'][0].lower() + s['screen'][1:]}: {s.get('credit') or 'sample ' + s['sample']}.*", ""]
    return "\n".join(out)


# ── the record-type pages ───────────────────────────────────────────────────────────────────────────────────────────
STANDARD_NOTE = ("Every record also has `name` (its id, in the address), `owner`, `creation`, `modified`, `modified_by` and "
                 "`docstatus` (0 a draft, 1 submitted, 2 cancelled), all read-only.")


def record_index(root: pathlib.Path = ROOT) -> dict:
    p = root / RECORDS / "index.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"release": "", "areas": [], "records": []}


def yes(v) -> str:
    return "yes" if v else ""


def field_table(fields: list[dict], have: set[str], src: str) -> str:
    rows = ["| Field | Field name | Type | Required | Read-only | Hidden | Links to |", "|---|---|---|---|---|---|---|"]
    for f in fields:
        to = record_link(f["links_to"], have, src) if f["links_to"] else (
            "one of: " + ", ".join(cell(c) for c in f["choices"][:12]) + (" …" if len(f["choices"]) > 12 else "") if f["choices"] else "")
        label = cell(f["label"]) + (" *(added by iVendNext)*" if f.get("added") else "")
        rows.append(f"| {label} | `{f['fieldname']}` | {f['type']} | {yes(f['required'])} | {yes(f['read_only'])} | {yes(f['hidden'])} | {to} |")
    return "\n".join(rows)


_NAMED: dict = {}


def samples_using(name: str, root: pathlib.Path = ROOT) -> list[str]:
    """The samples whose files name the record type (an API address, a manifest, a name in their text), by folder: the
    generator's own census, read once per build, so the page and the census agree."""
    if root not in _NAMED:
        import sys
        sys.path.insert(0, str(root / "tools" / "records"))
        import records as gen
        named = gen.named_by_kit(root)
        for n, where in gen.named_in_text(root).items():
            named.setdefault(n, set()).update(where)
        _NAMED[root] = named
    paths = _NAMED[root].get(name, set())
    return sorted({"/".join(p.split("/")[:2]) for p in paths if p.startswith("samples/")},
                  key=lambda s: int(re.sub(r"\D", "", s.split("/")[1].split("_")[0])))


def record_page(rec: dict, have: set[str], release: str, root: pathlib.Path = ROOT) -> tuple[str, str, str, str]:
    """(src, out, title, markdown) for one record type."""
    name, slug = rec["name"], rec["slug"]
    src = f"{RECORDS}/{slug}.md"
    addr = "/api/resource/" + urllib.parse.quote(name)
    lines = [f"# {name}", "", rec["lede"], "",
             f"**Area:** {rec['area']} · **Why it is here:** {rec['why']} · **Fields:** {len(rec['fields'])}"
             + (" · **Submitted** (booked) records: send `docstatus: 1` to book it as you create it, or submit a draft with `submit`."
                if rec["submittable"] and not rec.get("written_elsewhere") else "")
             + (" · **One record** (a settings record): read it at its own name." if rec["single"] else ""), ""]
    if rec.get("description"):
        lines += [f"*iVendNext's own description:* {rec['description']}", ""]
    lines += ["## Read and write it", "",
              "Every call runs as your app's own user, with its key in one header, at the retailer's own address. "
              f"The user reads and writes only what its role allows: [your app's user, and the rights the retailer gives it]({rel('recipes/integration_user.md', src)}).", "",
              "Read a list (only `name` unless you ask for `fields`):", "",
              "```bash", f"curl -s \"https://⟨site⟩{addr}?fields=%5B%22*%22%5D&limit_page_length=20\" \\",
              "  -H \"Authorization: token ⟨api key⟩:⟨api secret⟩\"", "```", "",
              "Read one, with its tables:" if rec["tables"] else "Read one:", "",
              "```bash", f"curl -s \"https://⟨site⟩{addr}/⟨name⟩\" -H \"Authorization: token ⟨api key⟩:⟨api secret⟩\"", "```", ""]
    if rec.get("written_elsewhere"):
        lines += [f"**Your app reads it; it does not write it here:** {rec['written_elsewhere']} All the record calls and their "
                  f"answers: [the API reference]({rel('site/pages/api.md', src)}).", ""]
    else:
        required = [f["fieldname"] for f in rec["fields"] if f["required"] and not f["read_only"]]
        body = ", ".join(f"\"{f}\": …" for f in required[:6]) or "\"⟨field⟩\": …"
        lines += [("Create one" + (" (the required fields first)" if required else "") + ", if your app's role may:"), "",
                  "```bash", f"curl -s -X POST \"https://⟨site⟩{addr}\" -H \"Authorization: token ⟨api key⟩:⟨api secret⟩\" \\",
                  f"  -H \"Content-Type: application/json\" -d '{{{body}}}'", "```", "",
                  f"Change one with `PUT {addr}/⟨name⟩` and the fields you change; a table sent there replaces its rows, so send its "
                  f"existing rows too. All the record calls and their answers: [the API reference]({rel('site/pages/api.md', src)}).", ""]
    used = samples_using(name, root)
    if used:
        lines += ["## Samples that use it", "", " · ".join(f"[{s.split('/')[1]}]({rel(s, src)})" for s in used), ""]
    lines += ["## Fields", "", f"Read from the product at {release or 'the kit’s pinned release'}: its own fields, the fields "
              "iVendNext adds to it, and iVendNext's changes to any of them. *Read-only* fields are set by iVendNext; a "
              "*hidden* one is not on the form but can be read. " + STANDARD_NOTE, "", field_table(rec["fields"], have, src), ""]
    for child, t in rec["tables"].items():
        holder = next((f for f in rec["fields"] if f["links_to"] == child), {})
        lines += [f"### Table: {child}", "", f"The rows of `{holder.get('fieldname', '')}`. Each row also has `idx` (its place), "
                  "`parent`, `parentfield` and `parenttype`.", "", field_table(t["fields"], have, src), ""]
    lines += ["---", "", f"[All record types](site:records/index.html) · [What you can use]({rel('site/pages/map.md', src)})", ""]
    return src, f"records/{slug}.html", f"Record type: {name}", "\n".join(lines)


def index_page(idx: dict) -> tuple[str, str, str, str]:
    src = f"{RECORDS}/index.md"
    recs = idx["records"]
    lines = ["# Record types and fields: what your app can read and write", "",
             f"The {len(recs)} record types an app most often reads or writes in a retailer's iVendNext, each with its fields: "
             "which are required, which are read-only, what each links to, and the address to read and write it. They are read "
             f"from the product itself at {idx.get('release') or 'the kit’s pinned release'}, with the fields iVendNext adds, and "
             "are read again at each release. Every other record type is reached the same way, at `/api/resource/⟨Record Type⟩`.", "",
             f"**{len(recs)} record types.** Browse by area, or find one in the A to Z list. Your own record types come from your "
             f"manifest ([what a manifest can add]({rel('site/pages/map.md', src)}#c-what-a-manifest-can-add)).", "",
             "**Areas:** " + " · ".join(f"[{a}](#{re.sub(r'[^\w\- ]', '', a.lower()).replace(' ', '-')})" for a in idx["areas"]
                                         if any(r["area"] == a for r in recs)), ""]
    for a in idx["areas"]:
        mine = [r for r in recs if r["area"] == a]
        if mine:
            lines += [f"## {a}", "", "| Record type | Fields | Tables | Why it is here |", "|---|---|---|---|"]
            lines += [f"| [{r['name']}](site:records/{r['slug']}.html) | {r['fields']} | {r['tables']} | {cell(r['why'])} |" for r in mine]
            lines.append("")
    lines += ["## A to Z", ""]
    letter = ""
    for r in sorted(recs, key=lambda r: r["name"].lower()):
        if r["name"][0].upper() != letter:
            letter = r["name"][0].upper()
            lines += ["", f"### {letter}", ""]
        lines.append(f"- [{r['name']}](site:records/{r['slug']}.html) — {r['area']}")
    lines.append("")
    return src, "records/index.html", "Record types", "\n".join(lines)


def record_pages(root: pathlib.Path = ROOT) -> list[tuple[str, str, str, str, str]]:
    """(src, out, title, markdown, description) for the index and every record type, from api/records/."""
    idx = record_index(root)
    have = {r["slug"] for r in idx["records"]}
    out = []
    src, o, t, md = index_page(idx)
    out.append((src, o, t, md, f"The {len(idx['records'])} record types an app reads or writes in a retailer's iVendNext, "
                                "each with its fields, which are required or read-only, and the address to read and write it."))
    for r in idx["records"]:
        rec = json.loads((root / RECORDS / f"{r['slug']}.json").read_text("utf-8"))
        src, o, t, md = record_page(rec, have, idx.get("release", ""), root)
        out.append((src, o, t, md, f"{rec['lede']} The {rec['name']} record type's fields, which are required or read-only, and how your app reads and writes it."))
    return out


# ── the build's check ───────────────────────────────────────────────────────────────────────────────────────────────
def errors(root: pathlib.Path = ROOT, d: dict | None = None) -> list[str]:
    """[] when the map holds every item of its sources and nothing they do not hold."""
    d = d or data()
    bad = []
    names = [n for n, _ in methods(root)]
    bad += [f"site/map.json: no line for the method {n} (api/README.md lists it)" for n in names if n not in d["methods"]]
    bad += [f"site/map.json: a line for the method {n}, which api/README.md does not list" for n in d["methods"] if n not in names]
    rows = {r["page"]: r for r in d["points"]}
    for stem in contract_pages(root):
        r = rows.get(stem)
        if not r:
            bad.append(f"site/map.json: contracts/pages/{stem}.md is in neither table of part (b)")
            continue
        if r["table"] not in ("calls", "declared"):
            bad.append(f"site/map.json: {stem}'s table is {r['table']!r}, not calls or declared")
            continue
        page = squash((root / POINTS / f"{stem}.md").read_text("utf-8"))
        for k, _ in (CALL_COLS if r["table"] == "calls" else DECLARED_COLS):
            q = r.get(k)
            if q is None:
                bad.append(f"site/map.json: {stem} has no {k!r} (write \"none\" when the page says nothing)")
            for piece in pieces(q) if q is not None else []:
                if squash(piece) not in page:
                    bad.append(f"site/map.json: {stem}'s {k!r} is not on contracts/pages/{stem}.md: {piece[:60]}")
    bad += [f"site/map.json: a part (b) row for {s}, which is not a page of contracts/pages/" for s in rows if s not in contract_pages(root)]
    for r in d.get("more_points", []):
        text = squash((root / r["source"]).read_text("utf-8"))
        for k, _ in (CALL_COLS if r["table"] == "calls" else DECLARED_COLS):
            for piece in pieces(r.get(k, "none")):
                if squash(piece) not in text:
                    bad.append(f"site/map.json: {r['name']}'s {k!r} is not on {r['source']}")
    keys = schema_keys(root)
    bad += [f"site/map.json: the manifest key {k} is in neither part (c) nor the keys that describe the app"
            for k in keys if k not in d["manifest"] and k not in d["app_keys"]]
    bad += [f"site/map.json: part (c) names {k}, which the manifest's schema does not hold" for k in d["manifest"] if k not in keys]
    bad += [f"site/map.json: {k} is a key that describes the app, but the manifest's schema does not hold it" for k in d["app_keys"] if k not in keys]
    for s in d["screens"]:
        shot = posixpath.normpath(posixpath.join(posixpath.dirname(MAP_SRC), s["shot"]))
        if not (root / shot).is_file():
            bad.append(f"site/map.json: the screen {s['screen']!r} has no picture at {shot}")
    idx = record_index(root)
    have = {r["name"] for r in idx["records"]}
    for _, path, _ in operations(root):
        t = record_type_of(path)
        if t and t not in have:
            bad.append(f"{SPEC}: {path} names the record type {t}, which has no record page (tools/records/records.py)")
    bad += [f"{RECORDS}/{r['slug']}.json is missing" for r in idx["records"] if not (root / RECORDS / f"{r['slug']}.json").is_file()]
    return bad
