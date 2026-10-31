"""One app from several of the kit's samples, a sample added to an app that exists, and the notice of newer samples.

    combine(samples, prefix, into) -> folder      New app: one app from one or more samples (``start.py s23 s22 --prefix``)
    add(sample, app_folder) -> Added              Add a sample (``start.py --add s22 --into apps/acme_hk``); also takes a
                                                  newer version of a sample the app already has
    newer(app_folder, index) -> [Newer]           each sample whose published version is higher than the app's

The merge rules, the same every time two or more samples are named:
  * each sample's names take its three-letter tag after the app's prefix: record types ``ACME HK TGR Settings``, fields
    ``acme_hk_tgr_…``; connection-point keys ``tgr_guard``; till keys, webhooks and roles the same way;
  * every sample's ``<PREFIX> Integration`` role is the single ``ACME HK Integration``, with the union of their rights;
  * the samples' event feeds are one registration, with the union of their record types;
  * the services are one service (``service/app.py``) that sends each call to its sample's part, mounted under ``/<tag>/``;
    a function unless a sample runs all the time; each sample's ``<TAG>_PREFIX`` setting is filled in and never shown.
An app made from one sample keeps its names untagged (``ACME HK Settings``). *Add a sample* never renames a name already
in the app: only the added sample's names take its tag.

The real product limits are refused in plain words (M01-M03), naming the samples; *Add a sample*'s
own refusals are M04 (an entry the developer changed) and M05 (a name the developer's code uses). A refusal writes
nothing: the app is written whole in a scratch folder and moved into place only when the kit's check passes.

The folder runs on its own: the template's helpers are copied into ``service/_kit/`` (each with a COPY header), each
sample's tests into ``tests/<tag>/`` with the kit's helpers they test with in ``tests/_kit/``, and ``README.md``,
``LICENSE``, ``THIRD_PARTY.md`` and ``.env.local`` are written for it. ``app.json`` holds the samples record:
``samples: [{name, version, kit_commit, tag, files: {path: sha256}, entries: {id: sha256}}]``, the hashes of what was
written, so *Add a sample* can tell what the developer changed. Standard library only.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import secrets as _secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
KIT = pathlib.Path(os.environ.get("PARTNER_KIT") or HERE.parents[1]).resolve()     # the kit whose samples and template it copies
sys.path.insert(0, str(HERE))
import rename  # noqa: E402
import sample_info  # noqa: E402
from site_rules import refusals as site_refusals  # noqa: E402
from validate import app_for, validate  # noqa: E402

TEMPLATE = KIT / "tools" / "app_template"
COMBINED = HERE / "combined"
SKIP_TOP = {"README.md", "manifest.json", "app.json", "Dockerfile", "screenshots", "tests", "__pycache__", ".env.local",
            ".env", "outside"}
TEXT = rename.TEXT
TEXT_NAMES = rename.TEXT_NAMES
RUNTIME_TOOL = re.compile(r"""(["'])\.\.\1\s*,\s*\1\.\.\1\s*,\s*\1tools\1\s*,\s*\1(\w+)\1|(["'])tools\3\s*,\s*\3(\w+)\3""")
TOOLS_REF = re.compile(r"""(?:["']tools["']\s*,\s*["']|/\s*["']tools["']\s*/\s*["']|\btools/)([a-z_]+)""")
COPY_HEADER = ("# COPY of the iVendNext partner kit's {path} at {commit}. A defect here is a defect there: report it on\n"
               "# the kit's board. Leave it as it is: Add a sample and a newer sample version replace it.\n")
POINT_KINDS = {"extension_subscriptions": None, "remote_keys": "remote_key", "webhooks": "webhook",
               "extension_modules": "module"}
KEYED = ("extension_subscriptions", "remote_keys", "webhooks", "extension_modules")
EVENT_WORDS = {"scan": ("at the scan", "scan"), "qty_change": ("when a quantity changes", "quantity"),
               "customer_add": ("when a customer is added", "customer"),
               "customer_select": ("when a customer is chosen", "customer")}
CHECKS_MAX, CHECK_SECONDS_MAX = 3, 10


class Refused(Exception):
    """A refusal in plain words: ``text`` for the command, ``page`` for the page."""

    def __init__(self, text: str, page: str | None = None, code: str = ""):
        super().__init__(text)
        self.text, self.page, self.code = text, page or text, code


# ---------------------------------------------------------------- small helpers

def sha(data) -> str:
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def kit_commit(kit: pathlib.Path = KIT) -> str:
    try:
        r = subprocess.run(["git", "-C", str(kit), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
                           timeout=10)
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def number(sample: str) -> str:
    m = re.match(r"s(\d+)_", sample)
    return f"S{m.group(1)}" if m else sample


def is_text(p: pathlib.Path) -> bool:
    return p.suffix.lower() in TEXT or p.name in TEXT_NAMES


def dump(data) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def bump_middle(v: str) -> str:
    a, b, _ = (list(sample_info.vtuple(v)) + [0, 0, 0])[:3]
    return f"{a}.{b + 1}.0"


# ---------------------------------------------------------------- one sample, as the app names it

@dataclasses.dataclass
class Part:
    sample: str                 # s23_till_guard
    folder: pathlib.Path        # the sample's folder in the kit
    title: str                  # Till guard rules
    tag: str                    # tgr
    tagged: bool                # names carry the tag (an app of several samples, or an added sample)
    prefix: str                 # the sample's names' prefix in the app: ACME HK TGR (or ACME HK untagged)
    app_name: str               # the sample's names' app part: acme_hk_tgr (or acme_hk)
    manifest: dict              # the sample's manifest, renamed (keys untagged: the sample's own view, for its tests)
    app_json: dict | None       # the sample's app.json, renamed (paths in the app)
    old: dict                   # the sample's manifest as the kit has it
    aliases: dict               # the name the sample's code uses for a point -> the app's name
    strip: bool                 # its routes did not start with /<tag>/: mounted under /<tag>/ and taken off on the way in
    feed: str | None = None     # its feed's name as renamed (merged into the app's one registration)
    own: dict | None = None     # the sample's manifest under its tagged prefix, its own role kept: what its own tests read

    @property
    def label(self) -> str:
        return f"{number(self.sample)} {self.title}"


def sample_folder(sample: str, samples_dir: pathlib.Path) -> pathlib.Path:
    if not re.fullmatch(r"[A-Za-z0-9_]+", sample or "") or not (samples_dir / sample).is_dir():
        raise Refused(f"No sample called {sample} in the kit.", code="no_sample")
    return samples_dir / sample


def resolve(name: str, samples_dir: pathlib.Path) -> str:
    """``s23``, ``S23`` or ``s23_till_guard`` -> the sample's folder name."""
    if (samples_dir / name).is_dir():
        return name
    m = re.fullmatch(r"[sS](\d+)", name or "")
    if m:
        hits = [p.name for p in samples_dir.iterdir() if p.is_dir() and re.match(rf"s{m.group(1)}_", p.name)]
        if len(hits) == 1:
            return hits[0]
    raise Refused(f"No sample called {name} in the kit.", code="no_sample")


def endpoint_path(url: str) -> str:
    return urllib.parse.urlsplit(url).path or "/"


def mount_url(url: str, tag: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=f"/{tag}{parts.path or '/'}"))


def make_part(sample: str, prefix: str, app: str, tagged: bool, samples_dir: pathlib.Path) -> Part:
    folder = sample_folder(sample, samples_dir)
    m = sample_info.manifest(folder)
    if not m or not isinstance(m.get("prefix"), str) or not isinstance(m.get("app"), str):
        raise Refused(f"{number(sample)} has no manifest of its own: it cannot be made into an app. Copy it by hand as "
                      "its README says.", code="no_manifest")
    words = m["prefix"].split()
    tag = (words[1] if len(words) > 1 else words[0]).lower()
    sp = f"{prefix} {tag.upper()}" if tagged else prefix
    sa = f"{app}_{tag}" if tagged else app
    out, left = rename.rename(m, sp)
    if left:
        raise Refused(f"{number(sample)}: a name is left after renaming ({left[0][:120]}). Copy it by hand.", code="rename")
    out["prefix"], out["app"] = sp, sa
    own = copy.deepcopy(out)
    integ_old, integ_new = f"{sp} Integration", f"{prefix} Integration"
    if tagged:
        out = rename._walk(out, lambda s: re.sub(rf"(?<![A-Za-z0-9]){re.escape(integ_old)}(?![A-Za-z0-9])", integ_new, s))
    aliases, strip = {}, False
    paths = [endpoint_path(x["endpoint_url"]) for k in KEYED for x in out.get(k) or [] if isinstance(x, dict)
             and isinstance(x.get("endpoint_url"), str)]
    if paths and tagged:
        strip = not all(p.startswith(f"/{tag}/") for p in paths)
    if tagged:
        for k in KEYED:
            for x in out.get(k) or []:
                key = x.get("key")
                if not isinstance(key, str):
                    continue
                if key.startswith(sa + "_"):               # a till key named after the app (pp_lyl_member)
                    aliases[app + key[len(sa):]] = key        # the code names it <app>_member
                else:
                    aliases[key] = f"{tag}_{key}"
    aj = sample_info.app_json(folder)
    if aj is not None:
        aj, _ = rename.rename_app_json(copy.deepcopy(aj), folder, None, sa)
    feed = None
    if out.get("registered_applications"):
        feed = out["registered_applications"][0].get("name")
    return Part(sample, folder, m.get("title") or sample, tag, tagged, sp, sa, out, aj, m, aliases, strip, feed, own)


# ---------------------------------------------------------------- the app's manifest

def identity(section: str, item) -> str:
    if not isinstance(item, dict):
        return str(item)
    if section == "custom_fields":
        return f"{item.get('dt')}.{item.get('fieldname')}"
    if section == "property_setters":
        return f"{item.get('doc_type')}.{item.get('field_name') or ''}.{item.get('property')}"
    if section == "links":
        return f"{item.get('doctype')}.{item.get('link_doctype')}.{item.get('link_fieldname')}"
    where = item.get("doctype") or item.get("ref_doctype") or item.get("dt") or item.get("doc_type")
    for k in ("key", "name", "role"):
        if isinstance(item.get(k), str):
            return item[k]
    for k in ("title", "label"):
        if isinstance(item.get(k), str):
            return f"{where}.{item[k]}" if isinstance(where, str) else item[k]
    return sha(item)[:16]


def ids(section: str, items) -> list[str]:
    """Each item's entry name in its list, unique: a second item with the same name is ``<name>#2``."""
    seen: dict = {}
    out = []
    for x in items or []:
        i = identity(section, x)
        seen[i] = seen.get(i, 0) + 1
        out.append(i if seen[i] == 1 else f"{i}#{seen[i]}")
    return out


def app_view(part: Part) -> dict:
    """The sample's manifest as the app holds it: keys tagged, routes mounted under /<tag>/ where needed."""
    m = copy.deepcopy(part.manifest)
    if part.tagged:
        for k in KEYED:
            for x in m.get(k) or []:
                if isinstance(x.get("key"), str):
                    x["key"] = part.aliases.get(x["key"], x["key"]) if not x["key"].startswith(part.app_name + "_") else x["key"]
    if part.strip:
        for k in KEYED:
            for x in m.get(k) or []:
                if isinstance(x.get("endpoint_url"), str):
                    x["endpoint_url"] = mount_url(x["endpoint_url"], part.tag)
        m["allowed_urls"] = [mount_url(u, part.tag) if isinstance(u, str) and any(
            u == y.get("endpoint_url") for k in KEYED for y in part.manifest.get(k) or []) else u
            for u in m.get("allowed_urls") or []]
    return m


def limits(parts: list[Part]) -> None:
    """The product's limits a set of samples can break together (M01-M03), in plain words."""
    by_event: dict = {}
    for p in parts:
        for s in p.manifest.get("extension_subscriptions") or []:
            if s.get("point") == "capture":
                ev = (s.get("settings") or {}).get("event")
                by_event.setdefault(ev, [])
                if p not in by_event[ev]:
                    by_event[ev].append(p)
    for ev, ps in by_event.items():
        if len(ps) > 1:
            ps = sorted(ps, key=lambda p: sample_info.vtuple(number(p.sample)[1:] + ".0.0"))
            where, noun = EVENT_WORDS.get(ev, (f"at {ev}", ev))
            a, b = ps[0], ps[1]
            names = " and ".join(p.label for p in ps) if len(ps) > 2 else f"{a.label} and {b.label}"
            raise Refused(f"These samples both capture {where}: {names}. A till event takes one capture. Untick one of "
                          f"them, or take {number(b.sample)}'s {noun} rule into {number(a.sample)}'s code by hand after the "
                          "app is made.", code="M01")
    checks = [(p, s) for p in parts for s in p.manifest.get("extension_subscriptions") or [] if s.get("point") == "check"]
    seconds = sum(float(s.get("timeout_seconds") or 0) for _, s in checks)
    if len(checks) > CHECKS_MAX or seconds > CHECK_SECONDS_MAX:
        listed = ", ".join(f"{s.get('label') or s.get('key')} ({number(p.sample)}, {float(s.get('timeout_seconds') or 0):g} s)"
                           for p, s in checks)
        raise Refused(f"This app would run {len(checks)} checks at Pay: {listed}. A sale runs at most 3 checks, 10 seconds "
                      "together. Untick one.", code="M02")
    readers = [p for p in parts if p.app_json and p.app_json.get("schedule")]
    if len(readers) > 1:            # one feed, one reader: two readers of one feed would take each other's events
        raise Refused(f"These samples both read the site's new sales and customers on their own: "
                      f"{' and '.join(p.label for p in readers)}. One app reads them once, so their two readers cannot "
                      "share it yet. Untick one of them.", code="readers")
    for p in parts:
        if routes(app_view(p)) and not handler_of(p):
            raise Refused(f"{p.label} answers the till from its own server, with no hosting order (app.json) the app's "
                          "one service can run. Untick it, or copy it by hand as its README says.", code="unhosted")
    owners: dict = {}
    for p in parts:
        for e in p.manifest.get("extension_modules") or []:
            owners.setdefault(e.get("point"), [])
            if p not in owners[e.get("point")]:
                owners[e.get("point")].append(p)
    for point, ps in owners.items():
        if len(ps) > 1:
            raise Refused(f"{ps[0].label} and {ps[1].label} both add a module at the same extension point ({point}). A "
                          "partner may add one module per extension point. Untick one.", code="M03")


def feed_name(prefix: str, base: dict | None = None) -> str:
    """The app's one event feed: the one it has already (an app started from one sample keeps its feed's name), else
    ``<prefix> Feed``."""
    for r in (base or {}).get("registered_applications") or []:
        if isinstance(r, dict) and isinstance(r.get("name"), str):
            return r["name"]
    return f"{prefix} Feed"


def build_manifest(parts: list[Part], prefix: str, app: str, base: dict | None = None) -> tuple[dict, dict]:
    """The app's manifest from its parts' views; and {entry id: the part samples that brought it}."""
    first = parts[0]
    if base is None:
        m = {"manifest_version": max(int(p.manifest.get("manifest_version") or 1) for p in parts), "app": app, "prefix": prefix,
             "title": " and ".join(p.title for p in parts) if len(parts) > 1 else first.title, "version": "1.0.0",
             "publisher": prefix.split()[0],
             "description": " ".join(f"{p.title}: {p.manifest.get('description') or ''}".strip() for p in parts)[:4000]}
    else:
        m = copy.deepcopy(base)
    owners: dict = {}
    multi_feed = len(parts) > 1 or any(p.tagged for p in parts)
    feed = feed_name(prefix, base)
    for p in parts:
        view = app_view(p)
        for section, items in view.items():
            if not isinstance(items, list):
                continue
            if section == "registered_applications" and multi_feed:
                for r in items:
                    merged = next((x for x in m.get(section) or [] if x.get("name") == feed), None)
                    if merged is None:
                        merged = {"name": feed, "description": "the app's service reads these events", "events": []}
                        m.setdefault(section, []).append(merged)
                    for e in r.get("events") or []:
                        if e not in merged["events"]:
                            merged["events"].append(e)
                    owners.setdefault(f"manifest:{section}:{feed}", []).append(p.sample)
                continue
            have = dict(zip(ids(section, m.get(section)), m.get(section) or []))
            for i, x in zip(ids(section, items), items):
                if i in have:
                    if have[i] == x:
                        continue
                    if section == "allowed_urls":
                        continue
                    if base is not None:        # Add a sample: the sample's value here; add() keeps what the developer changed
                        items_ = m[section]
                        items_[ids(section, items_).index(i)] = copy.deepcopy(x)
                        have[i] = x
                        owners.setdefault(f"manifest:{section}:{i}", []).append(p.sample)
                        continue
                    raise Refused(f"{p.label} and another sample both make {section} {i}: rename one of them by hand.",
                                  code="clash")
                m.setdefault(section, []).append(copy.deepcopy(x))
                have[i] = x
                owners.setdefault(f"manifest:{section}:{i}", []).append(p.sample)
    return m, owners


def check_manifest(m: dict) -> None:
    bad = [f"{r['where']} {r.get('name') or ''}: {r['reason']}" for r in validate(m) + site_refusals(m)]
    if bad:
        raise Refused("The kit's check refused the app's manifest: " + "; ".join(bad[:5]), code="M06")


def routes(m: dict) -> dict:
    """{route path: (kind, key, label)} for every connection point the manifest names."""
    out = {}
    for section in KEYED:
        for x in m.get(section) or []:
            url = x.get("endpoint_url")
            if not isinstance(url, str):
                continue
            path = endpoint_path(url)
            kind = POINT_KINDS[section] or x.get("point") or "check"
            if path in out and out[path][1] != x.get("key"):
                raise Refused(f"Two connection points answer the same route {path}: {out[path][1]} and {x.get('key')}. "
                              "Untick one.", code="route")
            out[path] = (kind, x.get("key"), x.get("label") or "")
    return out


# ---------------------------------------------------------------- app.json, the dispatcher, the folder's files

def build_app_json(parts: list[Part], app: str, base: dict | None = None) -> tuple[dict, dict, dict]:
    """The app's hosting order and its settings; {entry id: samples}; and {schedule name in the app: [tag, its name]}."""
    owners: dict = {}
    sched: dict = {}
    hosted = [p for p in parts if p.app_json]
    if base is None:
        aj = {"app": app.replace("_", "-"), "version": "1.0.0", "port": 8080, "health": "/health", "size": "small",
              "region": (hosted[0].app_json.get("region") if hosted else "us"), "shops": True, "runs": "function",
              "handler": "service/app.lambda_handler", "package": ["service"], "env": []}
    else:
        aj = copy.deepcopy(base)
    sizes = ["small", "medium", "large"]
    for p in hosted:
        pj = p.app_json
        if pj.get("runs") == "container" and aj.get("runs") != "container":
            aj["runs"] = "container"
            aj.pop("handler", None)
            aj.pop("package", None)
            owners.setdefault("app.json:runs", []).append(p.sample)
        if pj.get("size") in sizes and sizes.index(pj["size"]) > sizes.index(aj.get("size") or "small"):
            aj["size"] = pj["size"]
            owners.setdefault("app.json:size", []).append(p.sample)
        if pj.get("timeout") and int(pj["timeout"]) > int(aj.get("timeout") or 0):
            aj["timeout"] = int(pj["timeout"])
            owners.setdefault("app.json:timeout", []).append(p.sample)
        for name, rate in (pj.get("schedule") or {}).items():
            short = schedule_name(p.tag, name, aj.get("schedule") or {})
            aj.setdefault("schedule", {})[short] = rate
            sched[short] = [p.tag, name]
            owners.setdefault(f"app.json:schedule:{short}", []).append(p.sample)
        have = {e.get("name") for e in aj["env"]}
        for e in pj.get("env") or []:
            if e.get("name") == f"{p.tag.upper()}_PREFIX" or e.get("name") in have:
                continue
            aj["env"].append(copy.deepcopy(e))
            have.add(e.get("name"))
            owners.setdefault(f"app.json:env:{e.get('name')}", []).append(p.sample)
    if aj.get("runs") == "container":
        aj.pop("timeout", None)
        aj.pop("schedule", None)
        aj["port"] = 8000            # the README's docker run -p 8000:8000, the Dockerfile's EXPOSE and HEALTHCHECK
    return aj, owners, sched


def handler_of(part: Part) -> str | None:
    """The part's function entry inside service/: its hosting order's handler, or for one that runs all the time, its
    service's ``lambda_handler`` (every template-built service has one). None: no hosted service."""
    aj = part.app_json or {}
    if isinstance(aj.get("handler"), str):
        return f"{part.tag}/" + re.sub(rf"^(?:apps/[^/]+/|samples/{re.escape(part.sample)}/)", "", aj["handler"])
    if aj.get("runs") == "container" and "lambda_handler" in \
            ((part.folder / "service" / "app.py").read_text(encoding="utf-8") if (part.folder / "service" / "app.py").is_file() else ""):
        return f"{part.tag}/service/app.lambda_handler"
    return None


def schedule_name(tag: str, name: str, taken: dict) -> str:
    """The schedule's name in the app (1 to 11 characters, the hosting's rule): ``<tag>-<name>``, shortened with a number
    when it is longer; the dispatcher maps it back to the sample's own name (``schedules`` in dispatch.json)."""
    full = f"{tag}-{name}"
    if len(full) <= 11 and full not in taken:
        return full
    n = 1
    while f"{tag}-s{n}" in taken:
        n += 1
    return f"{tag}-s{n}"


def mount(part: Part, app_manifest: dict) -> dict:
    """The dispatcher's entry for one part."""
    handler = handler_of(part)          # None: a sample with no service of its own (lists and settings only)
    points = {}
    for path, (kind, key, label) in routes(app_view(part)).items():
        points[path] = {"kind": kind, "key": key, "label": label}
    return {"sample": part.sample, "title": part.title, "handler": handler, "prefix": part.prefix,
            "prefix_setting": f"{part.tag.upper()}_PREFIX", "aliases": part.aliases, "strip": part.strip, "points": points}


def entries_of(manifest: dict, app_json: dict, dispatch: dict) -> dict:
    """{entry id: value} of the three shared files the tool writes, compared entry by entry."""
    out = {}
    for k in ("title", "description", "publisher", "manifest_version"):
        if k in manifest:
            out[f"manifest:{k}"] = manifest[k]
    for section, items in manifest.items():
        if isinstance(items, list):
            for i, x in zip(ids(section, items), items):
                out[f"manifest:{section}:{i}"] = x
    for k, v in app_json.items():
        if k in ("env", "samples", "version", "schedule"):
            continue
        out[f"app.json:{k}"] = v
    for e in app_json.get("env") or []:
        out[f"app.json:env:{e.get('name')}"] = e
    for k, v in (app_json.get("schedule") or {}).items():
        out[f"app.json:schedule:{k}"] = v
    for tag, m in dispatch["mounts"].items():
        out[f"dispatch:{tag}"] = m
    for k, v in (dispatch.get("schedules") or {}).items():
        out[f"dispatch:schedule:{k}"] = v
    return out


def plain_entry(entry: str, manifest: dict) -> str:
    """An entry's name in plain words, for the page."""
    kind, _, rest = entry.partition(":")
    section, _, ident = rest.partition(":")
    if entry == "manifest:title":
        return "the app's title"
    if entry == "manifest:description":
        return "the app's description"
    if kind == "manifest" and section == "registered_applications":
        return "what the app reads from the site (new sales and customers)"
    if kind == "manifest" and section == "doctypes":
        return f"the list {ident}"
    if kind == "manifest" and section == "custom_fields":
        dt, _, f = ident.partition(".")
        return f"the field {f} on {dt}"
    if kind == "manifest" and section in KEYED:
        x = next((y for y in manifest.get(section) or [] if y.get("key") == ident), {})
        return f"the connection point {x.get('label') or ident}"
    if kind == "app.json" and section == "env":
        return f"the setting {ident}"
    if kind == "dispatch":
        return f"where the service sends the calls for /{section}/"
    return entry


def rewrite_text(text: str, part: Part, app: str, prefix: str, feed: str | None, code: bool = True) -> str:
    """One of the sample's files under the app's names (what start.py does for one sample), its kit paths made the app's."""
    import start  # noqa: E402  (start.py's rewrite: the same renaming a one-sample copy gets)
    text = start.rewrite(text, part.old, part.prefix, part.sample, part.app_name)
    text = text.replace(f"apps/{part.app_name}/", f"service/{part.tag}/").replace(f"apps/{part.app_name}", f"service/{part.tag}")
    if part.tagged and code:            # the app's one Integration role (a sample's own tests keep its own, as its view)
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(part.prefix)} Integration(?![A-Za-z0-9])", f"{prefix} Integration", text)
        if code and part.feed and feed and part.feed != feed:     # the service reads the app's one feed
            text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(part.feed)}(?![A-Za-z0-9])", feed, text)
    return text


def tools_used(folder: pathlib.Path) -> set:
    """The kit's tools a sample's code or tests reach (``tools/contracts``…), so its tests run outside the kit."""
    found = set()
    for p in folder.rglob("*.py"):
        found.update(TOOLS_REF.findall(p.read_text(encoding="utf-8", errors="ignore")))
    return {t for t in found if (KIT / "tools" / t).is_dir() and t not in ("app_template",)}


def part_files(part: Part, app: str, prefix: str, feed: str | None) -> dict:
    """{path in the app: bytes} for the files the sample brings: its code under service/<tag>/, its tests under
    tests/<tag>/ with the sample's own manifest and app.json as the app names them (for its tests only)."""
    out: dict = {}
    for p in sorted(part.folder.rglob("*")):
        rel = p.relative_to(part.folder)
        if not p.is_file() or rel.parts[0] in SKIP_TOP or "__pycache__" in rel.parts or p.suffix == ".pyc":
            continue
        out[f"service/{part.tag}/{rel.as_posix()}"] = p.read_bytes()
    if (part.folder / "README.md").is_file():            # a sample's own tests may read its README
        out[f"tests/{part.tag}/_README.md"] = (part.folder / "README.md").read_bytes()
    tests = part.folder / "tests"
    if tests.is_dir():
        for p in sorted(tests.rglob("*")):
            rel = p.relative_to(tests)
            if p.is_file() and "__pycache__" not in rel.parts and p.suffix != ".pyc":
                out[f"tests/{part.tag}/{rel.as_posix()}"] = p.read_bytes()
    runtime: set = set()                        # the kit's tools the service imports as it runs (feed_client)
    for path, data in list(out.items()):
        if is_text(pathlib.PurePosixPath(path)):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise Refused(f"{part.label}: {path} is not UTF-8 text. Copy this sample by hand.", code="text") from None
            text = rewrite_text(text, part, app, prefix, feed, code=path.startswith("service/"))
            if path.startswith("service/"):
                text = text.replace('"tools", "app_template", "service"', '"service", "_kit"')
                for m in RUNTIME_TOOL.finditer(text):
                    runtime.add(m.group(2) or m.group(4))
                text = RUNTIME_TOOL.sub(lambda m: (f'"..", "_kit", "{m.group(2)}"' if m.group(2)
                                                   else f'"service", "_kit", "{m.group(4)}"'), text)
            out[path] = text.encode("utf-8")
    commit = kit_commit()
    for t in sorted(runtime - {"app_template"}):
        for p in sorted((KIT / "tools" / t).rglob("*")):
            rel = p.relative_to(KIT / "tools" / t)
            if p.is_file() and not ({"tests", "__pycache__"} & set(rel.parts)) and p.suffix == ".py":   # code only
                data = COPY_HEADER.format(path=f"tools/{t}/{rel.as_posix()}", commit=commit).encode() + p.read_bytes()
                out[f"service/_kit/{t}/{rel.as_posix()}"] = data
    # the sample's own view, for its own tests: its names under its tagged prefix, its own feed and role
    own = copy.deepcopy(part.own or part.manifest)
    out[f"tests/{part.tag}/_manifest.json"] = dump(own).encode()
    if part.app_json:
        aj = copy.deepcopy(part.app_json)
        aj = json.loads(rewrite_text(json.dumps(aj, ensure_ascii=False), part, app, prefix, feed, code=False))
        out[f"tests/{part.tag}/_app.json"] = dump(aj).encode()
    for t in sorted(tools_used(part.folder)):
        for p in sorted((KIT / "tools" / t).rglob("*")):
            rel = p.relative_to(KIT / "tools" / t)
            if p.is_file() and not ({"tests", "__pycache__"} & set(rel.parts)) and p.suffix != ".pyc":
                out[f"tests/_kit/tools/{t}/{rel.as_posix()}"] = p.read_bytes()
    return out


def kit_files(commit: str) -> dict:
    """The template's helpers, copied into service/_kit/ with a COPY header; the one service and its tests."""
    out = {}
    for p in sorted((TEMPLATE / "service").glob("*.py")):
        if p.name in ("app.py", "core.py"):          # the template's example service, not a helper
            continue
        out[f"service/_kit/{p.name}"] = (COPY_HEADER.format(path=f"tools/app_template/service/{p.name}", commit=commit)
                                         + p.read_text(encoding="utf-8")).encode()
    out["service/app.py"] = (COMBINED / "app.py").read_bytes()
    out["tests/test_app.py"] = (COMBINED / "test_app.py").read_bytes()
    return out


def needs_install(parts: list[Part]) -> str | None:
    lines = []
    for p in parts:
        req = p.folder / "requirements.txt"
        if req.is_file():
            lines += [l.strip() for l in req.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return f"python3 -m pip install {' '.join(sorted(set(lines)))}" if lines else None


def does(part: Part) -> str:
    """What a sample puts in the app, in plain words: its own *What is in it* line, else its points."""
    line = re.search(r"^\*\*What is in it:\*\*\s*(.+?)\s*$", sample_info.readme(part.folder), re.M)
    if line:
        return line.group(1).rstrip(".")
    words = []
    for s in part.manifest.get("extension_subscriptions") or []:
        if s.get("point") == "capture":
            words.append(f"a capture on {(s.get('settings') or {}).get('event', 'the till').replace('_', ' ')}")
        elif s.get("point") == "check":
            words.append("a check at Pay")
        else:
            words.append(f"a {s.get('point')} point")
    words += ["a till key"] * len(part.manifest.get("remote_keys") or [])
    words += ["a notice of each sale"] * len(part.manifest.get("webhooks") or [])
    words += ["a button in Desk"] if part.manifest.get("desk_actions") else []
    lists = [d.get("name", "")[len(part.prefix) + 1:] for d in part.manifest.get("doctypes") or []]
    lists = [l.lower() for l in lists if l and l != "Settings"]
    out = list(dict.fromkeys(words)) + ([f"its lists ({', '.join(lists[:3])})"] if lists else [])
    return ", ".join(out) or "its lists and settings"


def in_folder(part: Part) -> str:
    """A part's line in the README's table: its title, and what it does at Pay or at the scan, when it does."""
    words = []
    for s in part.manifest.get("extension_subscriptions") or []:
        if s.get("point") == "check":
            words.append("the check at Pay")
        elif s.get("point") == "capture":
            words.append(f"the capture on {(s.get('settings') or {}).get('event', 'the till').replace('_', ' ')}")
    words = list(dict.fromkeys(words))
    if not words:
        return part.title
    return f"{part.title}, " + (words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1])


def where(part: Part) -> str:
    """The folder that holds a sample's part: its code, or, for a sample of lists and settings only, its tests."""
    has_code = any(p.is_file() and p.relative_to(part.folder).parts[0] not in SKIP_TOP for p in part.folder.rglob("*"))
    return f"service/{part.tag}/" if has_code else f"tests/{part.tag}/"


def readme(parts: list[Part], app: str, prefix: str, manifest: dict, app_json: dict) -> str:
    rows = "\n".join(f"| `{where(p)}` | {in_folder(p)} |" for p in parts)
    settings = list(app_json.get("env") or [])
    reads = "; ".join(f"`{e['name']}`: {e.get('purpose') or e.get('about') or ''}".rstrip(": ") for e in settings) or "none of its own"
    install = needs_install(parts)
    install_line = (f"One install first: `{install}`." if install else
                    "Nothing to install: the samples use Python's standard library.")
    if app_json.get("runs") == "container":
        server = (f"For an app that runs all the time: `docker build -t {app} .` then "
                  f"`docker run -p 8000:8000 --env-file .env {app}`.")
    else:
        server = "For one that runs only when called: `ivn package` writes `package.zip` for your own function host."
    names = ", ".join(p.label for p in parts)
    return f"""# {prefix}

{manifest.get('title')}: one app made by New app from {len(parts)} sample{'s' if len(parts) != 1 else ''} of the iVendNext partner kit ({names}). Its names start with `{prefix}` and `{app}`.

## What is in this folder

| Folder or file | What it is |
|---|---|
{rows}
| `service/app.py` | the one service: it sends each call to its sample's part, under `/<tag>/` |
| `manifest.json` | the lists, fields, keys and points the site installs |
| `app.json` | the app's name, version, settings and card |
| `tests/` | each sample's own tests, under this app's names (`tests/<tag>/`), and the app's own (`tests/test_app.py`) |
| `service/_kit/` | the kit's helpers the service needs, copied, so this folder runs on its own |
| `LICENSE`, `THIRD_PARTY.md` | your app's licence, and the notices of what it was made from |

## What you can change safely

Your own code in `service/`, the titles and words in `manifest.json`, the card.

## What to leave alone

Names already installed at a site; the samples record in `app.json`; `service/_kit/`. *Add a sample* keeps what you changed, and stops and says what when it would have to change it.

## Run it on your laptop

{install_line}

```
python3 -m unittest discover -s apps/{app}/tests
python3 apps/{app}/service/app.py --local
```

It reads test values from .env.local, which New app wrote for you; put your own outside keys there. It answers on http://localhost:8000.

## Run it on your own server

{server} It reads these settings: {reads}. Give it a public https address and put that address on Where the service runs.

## Change it with your AI assistant

Change it with your AI assistant: open your copy of the kit in it. It reads AGENTS.md, which knows this folder.
"""


def third_party(parts: list[Part], commit: str) -> str:
    lines = ["# Third-party components this app ships", "",
             "One list item per component, with its licence. This app was made from samples of the iVendNext partner kit:",
             ""]
    for p in parts:
        lines.append(f"- `service/{p.tag}/`: sample {p.label} (`{p.sample}`) of the iVendNext partner kit at {commit}, "
                     "Copyright 2026 CitiXsys, under the Apache License, Version 2.0")
    lines.append(f"- `service/_kit/`: the kit's app template helpers at {commit}, Copyright 2026 CitiXsys, under the Apache "
                 "License, Version 2.0; `service/_kit/ed25519.py` is adapted from the reference code of RFC 8032, Copyright "
                 "(c) 2017 IETF Trust and the persons identified as authors of the code, IETF Trust's BSD licence (the text "
                 "is in that file's header)")
    for p in parts:
        own = p.folder / "THIRD_PARTY.md"
        if own.is_file():
            lines += [l for l in own.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    return "\n".join(lines) + "\n"


def env_local(app: str, app_json: dict) -> str:
    lines = ["# Test values for your laptop, written by New app. Never a real secret: put your own outside keys here.",
             f"IVN_TEST_SECRET={_secrets.token_hex(24)}", f"IVN_LIBRARY_APP={app}", "IVN_SHOPS_FILE=.local/shops.json"]
    for e in app_json.get("env") or []:
        n = e.get("name")
        if n in ("IVN_LIBRARY_APP",) or not isinstance(n, str):
            continue
        val = ".local/state" if n == "PP_STATE" else ("http://localhost:8000" if n.endswith(("_URL", "_API")) else "test-value")
        lines.append(f"# {e.get('purpose') or e.get('about') or ''}".rstrip())
        lines.append(f"{n}={val}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- the whole app, written in one go

def write_folder(target: pathlib.Path, files: dict) -> None:
    root = target.resolve()
    for path, data in files.items():
        p = target / path
        if ".." in pathlib.PurePosixPath(path).parts or any(q.is_symlink() for q in [p, *p.parents] if q != q.parent):
            raise Refused(f"{path} is a link or leaves the app's folder: nothing is written through it.", code="link")
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.parent.resolve().is_relative_to(root):
            raise Refused(f"{path} leaves the app's folder: nothing is written there.", code="link")
        p.write_bytes(data)


def kit_check(folder: pathlib.Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", str(KIT / "tools" / "check" / "check.py"), str(folder)],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    lines = r.stdout.strip().splitlines() or ["(no verdict)"]
    why = [l.split(None, 1)[-1] for l in lines if l.startswith("REFUSED")]
    return r.returncode, lines[-1] + ("" if not why else ": " + "; ".join(why[:5]))


def run_tests(folder: pathlib.Path) -> tuple[bool, int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("IVN_", "LIBRARY_"))}
    env.update(PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], cwd=folder,
                       capture_output=True, text=True, env=env, timeout=3600)
    ran = sum(int(n) for n in re.findall(r"^SAMPLE \S+ ran=(\d+)", r.stderr, re.M))
    own = re.findall(r"^Ran (\d+) tests?", r.stderr, re.M)
    total = ran + (int(own[-1]) if own else 0)
    return r.returncode == 0, total, r.stderr


def assemble(parts: list[Part], prefix: str, app: str, commit: str, base_manifest=None, base_app_json=None,
             base_dispatch=None) -> tuple[dict, dict, dict, dict, dict]:
    """(manifest, app.json, dispatch, files, owners) for these parts on top of what the app has."""
    limits(parts)
    manifest, owners = build_manifest(parts, prefix, app, base_manifest)
    routes(manifest)
    check_manifest(manifest)
    app_json, aj_owners, sched = build_app_json(parts, app, base_app_json)
    owners.update({k: owners.get(k, []) + v for k, v in aj_owners.items()})
    dispatch = copy.deepcopy(base_dispatch) if base_dispatch else {"app": app, "prefix": prefix, "mounts": {}}
    feed = feed_name(prefix, base_manifest) if len(parts) > 1 or any(p.tagged for p in parts) else None
    files: dict = {}
    dispatch.setdefault("schedules", {}).update(sched)
    for p in parts:
        dispatch["mounts"][p.tag] = mount(p, manifest)
        owners.setdefault(f"dispatch:{p.tag}", []).append(p.sample)
        files.update(part_files(p, app, prefix, feed))
    return manifest, app_json, dispatch, files, owners


def leftovers(files: dict, parts: list[Part]) -> list[str]:
    import start  # noqa: E402
    found = []
    for p in parts:
        pat = start.old_names(p.old, p.sample)
        for path, data in files.items():
            if not path.startswith((f"service/{p.tag}/", f"tests/{p.tag}/")) or not is_text(pathlib.PurePosixPath(path)):
                continue
            for n, line in enumerate(data.decode("utf-8").splitlines(), 1):
                if pat.search(line):
                    found.append(f"{path}:{n}: {line.strip()[:100]}")
    return found


UNRECORDED = ("app.json", "manifest.json", "service/dispatch.json", ".env.local")


def owner_of(path: str, parts: list[Part], owners: dict) -> str:
    """The sample whose record holds a file: its own part's, else the app's first sample's."""
    for p in parts:
        if path.startswith((f"service/{p.tag}/", f"tests/{p.tag}/")):
            return p.sample
    return parts[0].sample


def records(parts: list[Part], files: dict, entries: dict, owners: dict, commit: str) -> list[dict]:
    """The samples record: each sample, its version, and the hash of every file and entry the tool wrote, each in exactly
    one sample's record (its own part's, else the sample that brought it, else the first sample's)."""
    out = {p.sample: {"name": p.sample, "version": sample_info.version(p.folder) or "1.0.0", "kit_commit": commit,
                      "tag": p.tag, "tagged": p.tagged, "files": {}, "entries": {}} for p in parts}
    for path, data in files.items():
        if path not in UNRECORDED and not path.startswith(".samples/"):
            out[owner_of(path, parts, owners)]["files"][path] = sha(data)
    names = {p.sample for p in parts}
    for i, v in entries.items():
        who = next((s for s in owners.get(i, []) if s in names), parts[0].sample)
        out[who]["entries"][i] = sha(v)
    for r in out.values():
        r["files"], r["entries"] = dict(sorted(r["files"].items())), dict(sorted(r["entries"].items()))
    return [out[p.sample] for p in parts]


def _finish(target: pathlib.Path, staged: pathlib.Path) -> None:
    """Move the staged folder into place: the old one (if any) is removed only after the new one is in place."""
    backup = None
    if target.exists():
        backup = pathlib.Path(tempfile.mkdtemp(prefix=f".{target.name}.before-add.", dir=target.parent))
        backup.rmdir()
        target.rename(backup)
    try:
        staged.rename(target)
    except OSError:
        if backup is not None:
            backup.rename(target)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def combine(samples, prefix: str, into, test: bool = False, samples_dir=None, out=None) -> pathlib.Path:
    """New app: one app in ``<into>/apps/<app>/`` from one or more samples. Returns the folder; raises Refused."""
    import start  # noqa: E402
    samples_dir = pathlib.Path(samples_dir) if samples_dir else KIT / "samples"
    names = [resolve(s, samples_dir) for s in samples]
    if not names:
        raise Refused("Tick at least one sample.", code="none")
    if len(set(names)) != len(names):
        raise Refused("A sample is named twice: name each once.", code="twice")
    start.refuse_new_prefix(prefix, "")
    app = app_for(prefix)
    into = pathlib.Path(into).resolve()
    target = into / "apps" / app
    if target.exists():
        raise Refused(f"apps/{app} exists already: pick another name, or add a sample to it.", code="exists")
    tagged = len(names) > 1
    parts = [make_part(s, prefix, app, tagged, samples_dir) for s in names]
    tags = [p.tag for p in parts]
    if len(set(tags)) != len(tags):
        raise Refused("Two of these samples carry the same short tag: untick one.", code="tag")
    commit = kit_commit()
    manifest, app_json, dispatch, files, owners = assemble(parts, prefix, app, commit)
    left = leftovers(files, parts)
    if left:
        raise Refused("A name of a sample is still in the app, so it is not finished:\n  " + "\n  ".join(left[:20]), code="left")
    files.update(kit_files(commit))
    files["README.md"] = readme(parts, app, prefix, manifest, app_json).encode()
    files["LICENSE"] = (TEMPLATE / "LICENSE").read_bytes()
    files["THIRD_PARTY.md"] = third_party(parts, commit).encode()
    files[".env.local"] = env_local(app, app_json).encode()
    files[".gitignore"] = b".env.local\n.env\n.local/\n__pycache__/\n"
    if app_json.get("runs") == "container":
        files["Dockerfile"] = dockerfile().encode()
    entries = entries_of(manifest, app_json, dispatch)
    app_json["samples"] = records(parts, files, entries, owners, commit)
    files["manifest.json"] = dump(manifest).encode()
    files["app.json"] = dump(app_json).encode()
    files["service/dispatch.json"] = dump(dispatch).encode()
    (into / "apps").mkdir(parents=True, exist_ok=True)
    staged = pathlib.Path(tempfile.mkdtemp(prefix=f".{app}.", dir=into / "apps"))
    try:
        write_folder(staged, files)
        rc, verdict = kit_check(staged)
        if rc:
            raise Refused(f"Not made: the kit's check refused the app. {verdict}", code="M06")
        summary = summary_lines(parts, verdict, None)
        if test:
            ok, total, log = run_tests(staged)
            if not ok:
                raise Refused("Not made: the app's tests fail under its names:\n" + log[-2500:], code="tests")
            summary = summary_lines(parts, verdict, total)
        _finish(target, staged)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
    if out is not None:
        for line in summary:
            print(line, file=out)
        print(f"Folder: apps/{app}/ ({', '.join(where(p) for p in parts if where(p).startswith('service/'))}, manifest.json, app.json, tests/). "
              "Read its README.md: what is in it and what you can change.", file=out)
    return target


def summary_lines(parts: list[Part], verdict: str, tests: int | None) -> list[str]:
    green = "CHECK GREEN" if "GREEN" in verdict.upper() else verdict
    n = len(parts)
    head = f"Made. {n} sample{'s' if n != 1 else ''}, 1 app. {green}"
    if tests is not None:
        head += f" · {tests} tests run, {tests} passed."
    else:
        head += "."
    what = ", ".join(f"{p.title} ({p.tag}: {does(p)})" for p in parts)
    feeds = "one feed" if any(p.manifest.get("registered_applications") for p in parts) else "no feed"
    return [head, f"What is in it: {what}. One service, {feeds}, one app user."]


def dockerfile() -> str:
    return ("FROM python:3.12-slim\nWORKDIR /app\nCOPY service/ service/\nENV PORT=8000\nEXPOSE 8000\nUSER 1000\n"
            "HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c \"import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)\"\n"
            "CMD [\"python3\", \"service/app.py\"]\n")


# ---------------------------------------------------------------- Add a sample

@dataclasses.dataclass
class Added:
    sample: str
    label: str
    version: str                # the app's new version
    kept_files: list
    kept_entries: list
    saved: str | None           # .samples/<sample>-<version>/ when a copy of a changed file was saved there

    def lines(self, manifest: dict | None = None) -> list[str]:
        out = [f"Added to a new draft {self.version}, on no site yet."]
        kept = list(self.kept_files) + [plain_entry(e, manifest or {}) for e in self.kept_entries]
        if kept:
            out.append(f"Your changes are kept: {kept[0] if len(kept) == 1 else ', '.join(kept[:-1]) + ' and ' + kept[-1]}.")
        if self.saved:
            out.append(f"{number(self.sample)}'s own copy of a file you changed is saved beside it in {self.saved} for your "
                       "developer to compare.")
        return out


def m04(part_label: str, sample: str, entry: str, manifest: dict) -> Refused:
    n = number(sample)
    return Refused(f"Not added: {n} must change the entry {entry}, which you changed. Nothing in your app was changed. "
                   f"Put that entry back as it was, or add {n}'s part by hand.",
                   f"Not added: {n} must change the entry {plain_entry(entry, manifest)}, which you changed. Nothing in "
                   f"your app was changed. Ask your developer to put that entry back, or to add {n}'s part by hand.",
                   code="M04")


def m05(sample: str, name: str) -> Refused:
    n = number(sample)
    return Refused(f"Not added: {n} needs the name {name}, which your own code already uses. Nothing in your app was "
                   f"changed. Rename yours, then add {n} again.", code="M05")


def own_texts(app_folder: pathlib.Path, recorded: dict) -> dict:
    """{path: text} of the developer's own text files: every file the samples record does not hold, or holds changed."""
    out = {}
    for p in sorted(app_folder.rglob("*")):
        rel = p.relative_to(app_folder).as_posix()
        if not p.is_file() or rel.startswith((".samples/", ".local/", "tests/_kit/", "service/_kit/")) or "__pycache__" in rel \
                or rel in ("app.json", "manifest.json", "service/dispatch.json", ".env.local"):
            continue
        data = p.read_bytes()
        if rel in recorded and recorded[rel] == sha(data):
            continue
        if is_text(p):
            try:
                out[rel] = data.decode("utf-8")
            except UnicodeDecodeError:
                pass
    return out


def names_of(view: dict) -> set:
    """The names an app part makes on a site: record types, fields, keys, roles."""
    out = set()
    for d in view.get("doctypes") or []:
        out.add(d.get("name"))
    for f in view.get("custom_fields") or []:
        out.add(f.get("fieldname"))
    for k in KEYED:
        for x in view.get(k) or []:
            out.add(x.get("key"))
    return {n for n in out if isinstance(n, str) and n}


def links_in(folder: pathlib.Path) -> list[str]:
    return [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_symlink()]


def add(sample: str, app_folder, samples_dir=None, test: bool = False, out=None) -> Added:
    """Add a sample to an app made by New app, keeping every change of the developer's; all or nothing. Adding a
    sample the app already has takes its newer version (*Take it*) by the same rules."""
    samples_dir = pathlib.Path(samples_dir) if samples_dir else KIT / "samples"
    app_folder = pathlib.Path(app_folder).resolve()
    name = resolve(sample, samples_dir)
    try:
        cur_manifest = json.loads((app_folder / "manifest.json").read_text(encoding="utf-8"))
        cur_app = json.loads((app_folder / "app.json").read_text(encoding="utf-8"))
        cur_dispatch = json.loads((app_folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused(f"{app_folder} is not an app made by New app (it has no manifest.json, app.json and "
                      "service/dispatch.json): make the app with New app first, then add a sample to it.",
                      code="not_an_app") from None
    record = cur_app.get("samples")
    if not isinstance(record, list) or not record:
        raise Refused("This app has no samples record in its app.json, so Add a sample cannot tell what you changed. "
                      "Make the app again with New app, then bring your changes into it.", code="no_record")
    links = links_in(app_folder)
    if links:
        raise Refused(f"Not added: {links[0]} is a link, and Add a sample never writes through a link. Nothing in your "
                      "app was changed. Put the file itself there, then add the sample again.", code="link")
    prefix, app = cur_manifest["prefix"], cur_manifest["app"]
    again = next((r for r in record if r["name"] == name), None)
    # names already in the app are never renamed: a sample the app has keeps its form; a new one carries its tag
    tagged = bool(again.get("tagged", True)) if again else True
    part = make_part(name, prefix, app, tagged, samples_dir)
    others = [make_part(r["name"], prefix, app, bool(r.get("tagged", True)), samples_dir) for r in record
              if r["name"] != name and (samples_dir / r["name"]).is_dir()]
    if again is None and part.tag in {r.get("tag") for r in record}:
        raise m05(name, f"the tag {part.tag} (another sample of this app carries it)")
    if again is None and ((app_folder / "service" / part.tag).exists() or (app_folder / "tests" / part.tag).exists()):
        raise m05(name, f"service/{part.tag}/")
    limits(others + [part])                               # M01-M03 over the whole app, in plain words
    commit = kit_commit()
    rec_files: dict = {}
    rec_entries: dict = {}
    for r in record:
        for path, h in r.get("files", {}).items():
            rec_files[path] = (r["name"], h)
        for i, h in r.get("entries", {}).items():
            rec_entries[i] = (r["name"], h)
    cur_entries = entries_of(cur_manifest, cur_app, cur_dispatch)
    new_manifest, new_app, new_dispatch, files, owners = assemble([part], prefix, app, commit, cur_manifest, cur_app,
                                                                   cur_dispatch)
    new_entries = entries_of(new_manifest, new_app, new_dispatch)
    # entries, one by one
    take: dict = {}                                       # entry id -> the tool's value, written
    kept_entries: list = []
    for i, v in new_entries.items():
        cur, rec = cur_entries.get(i), rec_entries.get(i)
        if cur is None and rec is None:
            take[i] = v                                   # new
        elif cur is None:                                 # the developer removed it
            if sha(v) != rec[1]:
                raise m04(part.label, name, i, cur_manifest)
            kept_entries.append(i)
        elif sha(cur) == sha(v):
            take[i] = v
        elif rec is None:                                 # the developer's own entry, which the sample would replace
            raise m05(name, i.split(":", 2)[-1])
        elif sha(v) == rec[1]:                            # the sample does not change it: the developer's stays
            kept_entries.append(i)
        elif sha(cur) != rec[1]:                          # the developer changed it, and the sample must change it
            raise m04(part.label, name, i, cur_manifest)
        else:
            take[i] = v
    # every other entry the developer changed or removed, named as kept
    kept_entries += [i for i, (_, h) in rec_entries.items() if i not in kept_entries and
                     (i not in cur_entries or sha(cur_entries[i]) != h) and not (i in take and sha(take[i]) == h)]
    kept_entries = sorted(set(kept_entries))
    # the developer's own code must not already use a name the sample brings
    if again is None:
        own = own_texts(app_folder, {p: h for p, (_, h) in rec_files.items()})
        for n in sorted(names_of(app_view(part)) - names_of(cur_manifest)):
            for path, text in own.items():
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])", text):
                    raise m05(name, n)
    # files, whole: the sample's own and the tool's (the kit's helpers, the one service, the README)
    tool_files = {k: v for k, v in kit_files(commit).items()}
    ver = sample_info.version(part.folder) or "1.0.0"
    saved_dir = f".samples/{name.split('_', 1)[0]}-{ver}/"
    write, written, kept_files, saved = {}, {}, [], False
    for path, data in {**tool_files, **files}.items():
        p = app_folder / path
        rec = rec_files.get(path)
        if not p.exists():
            if rec is None:
                write[path] = written[path] = data
            else:                                         # the developer removed it: kept removed, the sample's copy saved
                kept_files.append(path)
                write[saved_dir + path] = data
                saved = True
                written[path] = data
            continue
        cur = p.read_bytes()
        if cur == data:
            written[path] = data
            continue
        if rec is None:
            raise m05(name, path)
        if sha(cur) != rec[1]:                            # the developer changed it: kept, the sample's copy beside it
            kept_files.append(path)
            if path.startswith((f"service/{part.tag}/", f"tests/{part.tag}/")):
                write[saved_dir + path] = data
                saved = True
            written[path] = data
        else:
            write[path] = written[path] = data
    for path, (_, h) in sorted(rec_files.items()):        # every other file of the developer's, named as kept
        p = app_folder / path
        if path not in written and path not in kept_files and (not p.is_file() or sha(p.read_bytes()) != h):
            kept_files.append(path)
    kept_files = sorted(set(kept_files))
    # the three shared files: the app as it is, with the tool's entries taken
    final_manifest, final_app, final_dispatch = (copy.deepcopy(cur_manifest), copy.deepcopy(cur_app),
                                                 copy.deepcopy(cur_dispatch))
    for i, v in take.items():
        _set_entry(final_manifest, final_app, final_dispatch, i, v)
    version = bump_middle(cur_app.get("version") or "1.0.0")
    final_manifest["version"] = final_app["version"] = version
    # the record: the hash of what the tool wrote (or would have, for what the developer kept), each in one record
    all_parts = [p for p in others] + [part]
    by_name = {r["name"]: copy.deepcopy(r) for r in record}
    new_rec = by_name.get(name) or {"name": name, "files": {}, "entries": {}}
    new_rec.update({"name": name, "version": ver, "kit_commit": commit, "tag": part.tag, "tagged": part.tagged})
    by_name[name] = new_rec
    for path, data in written.items():
        if path in rec_files:
            holder = rec_files[path][0]
        elif path.startswith((f"service/{part.tag}/", f"tests/{part.tag}/")):
            holder = name
        else:
            holder = record[0]["name"]
        by_name[holder]["files"][path] = sha(data)
    for i, v in new_entries.items():
        if i in take or i in kept_entries:
            holder = rec_entries.get(i, (name, None))[0]
            if i in take or i in rec_entries:
                by_name[holder]["entries"][i] = sha(v)
    order = [r["name"] for r in record] + ([name] if again is None else [])
    final_app["samples"] = [by_name[n] for n in order]
    for r in final_app["samples"]:
        r["files"], r["entries"] = dict(sorted(r["files"].items())), dict(sorted(r["entries"].items()))
    final_dispatch["mounts"][part.tag] = new_dispatch["mounts"][part.tag]
    final_dispatch.setdefault("schedules", {}).update(new_dispatch.get("schedules") or {})
    # README and the notices: rewritten unless the developer changed them (the same file rule)
    first = record[0]["name"]
    ordered = [pp for n in order for pp in all_parts if pp.sample == n]
    for path, data in (("README.md", readme(ordered, app, prefix, final_manifest, final_app).encode()),
                       ("THIRD_PARTY.md", third_party(ordered, commit).encode())):
        p, rec = app_folder / path, rec_files.get(path)
        if p.is_file() and rec is not None and sha(p.read_bytes()) == rec[1]:
            write[path] = data
            by_name[rec[0]]["files"][path] = sha(data)
        elif p.is_file() and rec is not None and path not in kept_files:
            kept_files.append(path)
    # .env.local: the developer's own keys stay; a setting the sample brings is added with a test value
    env_path = app_folder / ".env.local"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        have = {l.split("=", 1)[0].strip() for l in text.splitlines() if "=" in l and not l.startswith("#")}
        extra = [e for e in final_app.get("env") or [] if e.get("name") not in have and e.get("name") != "IVN_LIBRARY_APP"]
        if extra:
            lines = env_local(app, {"env": extra}).splitlines()[4:]
            write[".env.local"] = (text.rstrip("\n") + "\n" + "\n".join(lines) + "\n").encode()
    write["manifest.json"] = dump(final_manifest).encode()
    write["app.json"] = dump(final_app).encode()
    write["service/dispatch.json"] = dump(final_dispatch).encode()
    check_manifest(final_manifest)
    staged = pathlib.Path(tempfile.mkdtemp(prefix=f".{app_folder.name}.", dir=app_folder.parent))
    try:
        shutil.rmtree(staged)
        shutil.copytree(app_folder, staged, symlinks=True)
        write_folder(staged, write)
        rc, verdict = kit_check(staged)
        if rc:
            raise Refused(f"Not added: the kit's check refused the result. {verdict}. Nothing in your app was changed.",
                          code="M06")
        if test:
            ok, total, log = run_tests(staged)
            if not ok:
                raise Refused("Not added: the app's tests fail with the sample in it. Nothing in your app was changed.\n"
                              + log[-2500:], code="tests")
        _finish(app_folder, staged)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
    result = Added(name, part.label, version, sorted(set(kept_files)), kept_entries, saved_dir if saved else None)
    if out is not None:
        for line in result.lines(final_manifest):
            print(line, file=out)
    return result


def _set_entry(manifest: dict, app_json: dict, dispatch: dict, entry: str, value) -> None:
    kind, _, rest = entry.partition(":")
    if kind == "app.json":
        _set_app_entry(app_json, entry, value)
        return
    if kind == "dispatch":
        section, _, ident = rest.partition(":")
        if section == "schedule":
            dispatch.setdefault("schedules", {})[ident] = value
        else:
            dispatch["mounts"][section] = value
        return
    section, _, ident = rest.partition(":")
    if not ident:
        manifest[section] = value
        return
    items = manifest.setdefault(section, [])
    names = ids(section, items)
    if ident in names:
        items[names.index(ident)] = copy.deepcopy(value)
    else:
        items.append(copy.deepcopy(value))


def _set_app_entry(app_json: dict, entry: str, value) -> None:
    _, _, rest = entry.partition(":")
    key, _, ident = rest.partition(":")
    if key == "env":
        for i, e in enumerate(app_json.setdefault("env", [])):
            if e.get("name") == ident:
                app_json["env"][i] = copy.deepcopy(value)
                return
        app_json["env"].append(copy.deepcopy(value))
    elif key == "schedule":
        app_json.setdefault("schedule", {})[ident] = value
    else:
        app_json[key] = copy.deepcopy(value)
        if key == "runs" and value == "container":
            app_json.pop("handler", None)
            app_json.pop("package", None)


# ---------------------------------------------------------------- newer versions

@dataclasses.dataclass
class Newer:
    sample: str
    title: str
    yours: str
    version: str
    lines: list                 # [(version, [its Versions lines])], newest first, each newer than yours

    def text(self) -> str:
        return (f"A newer version of {number(self.sample)} {self.title} is available: {self.version} (yours is "
                f"{self.yours}).")


def load_index(source) -> dict:
    """The published samples index: a dict, a path, or an https address."""
    if isinstance(source, dict):
        return source
    s = str(source)
    if s.startswith("https://"):
        import urllib.request
        with urllib.request.urlopen(s, timeout=10) as r:
            return json.loads(r.read())
    return json.loads(pathlib.Path(s).read_text(encoding="utf-8"))


def newer(app_folder, index) -> list[Newer]:
    """Each sample of the app whose version in the index is higher than the one the app records, with the *Versions*
    lines since. It only tells: taking a newer version is the developer's choice (``add`` with that sample)."""
    record = json.loads((pathlib.Path(app_folder) / "app.json").read_text(encoding="utf-8")).get("samples") or []
    idx = {s.get("name"): s for s in load_index(index).get("samples") or [] if isinstance(s, dict)}
    out = []
    for r in record:
        s = idx.get(r.get("name"))
        if not s or sample_info.vtuple(s.get("version")) <= sample_info.vtuple(r.get("version")):
            continue
        lines = [(v.get("version"), list(v.get("lines") or [])) for v in s.get("versions") or []
                 if sample_info.vtuple(v.get("version")) > sample_info.vtuple(r.get("version"))]
        out.append(Newer(r["name"], s.get("title") or r["name"], r.get("version"), s["version"], lines))
    return out
