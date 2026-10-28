#!/usr/bin/env python3
"""Plan an app for CitiXsys App Hosting, and order it online: check it, refuse what the service refuses, print what it
would create; then `order` it, pay, and run it (`order`, `status`, `secret`, `cancel`: `hosting_order.py`).

    python3 tools/deploy_app/deploy_app.py <app folder> --image <registry>/<repo>:<version> --plan starter --partner <you>
                                           [--env prod|staging|sandbox] [--customer <name>] [--json]
    python3 tools/deploy_app/deploy_app.py <app folder> --zip <out.zip> [--root <folder>] --plan starter --partner <you> …

An app whose `app.json` says `"runs": "function"` (a press-only app: a till key, a check, a webhook; chapter 14b) is
hosted as a function paid per call, not an always-on container (an app with background work too, when its `schedule`
runs it: a feed pass, a daily job, each call at most its `timeout`, 900 seconds): it takes `--zip`, where this tool writes the package
(the `package` paths of `app.json`, read from `--root`, by default the app's folder; never a file whose name starts with
a dot, never `__pycache__`), and no `--image`. An app that says nothing about `runs` is a container, exactly as before.

It reads the app's settings file (`app.json`) and Dockerfile, checks them with the template's own checker
(`tools/app_template/validate_app.py`) and its licence file and third-party list with the intake's licence check
(`tools/check/licence.py --hosted`: an AGPL component needs its published source), then checks the image and the plan: the image is tagged with the app's version
(never `latest`), the size and the copy (prod, staging, sandbox) are ones the plan allows, the region is one we serve,
the name is not reserved. It prints the address, the size, what the plan enforces and includes, the block the service
adds to its infrastructure, and the order to put it live in. Planning changes nothing anywhere. Ordering is its own
command (`deploy_app.py order …`, guide 14b *Order and pay online*): signed with your publishing key, paid online, and
built by the hosting with no person. Exit code: 0 planned · 1 refused · 2 usage.
Standard library only. The plans are data: `plans.json` beside this file, prices included. This tool prints no price.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app_template"))
import validate_app  # noqa: E402  (the template's checker, reused, never copied)
sys.path.insert(0, str(HERE.parent / "check"))
import licence  # noqa: E402  (the intake's licence check, with the hosted rule)

PLANS = json.loads((HERE / "plans.json").read_text("utf-8"))
SLUG = re.compile(r"[a-z][a-z0-9-]{1,30}")
# <registry host>/<path>:<tag>. The service copies the image into the app's own registry under the same tag.
FUNCTION_MB = 512   # every function's memory; its speed comes with it
# What a function gets on any plan (plans.json's "includes" describe an always-on container: a function has none)
FUNCTION_INCLUDES = [{"what": "an HTTPS address, answered only when a shop calls", "live": True},
                     {"what": "each shop's secrets kept in the app's own encrypted table", "live": True},
                     {"what": "logs", "live": True},
                     {"what": "a notice before each iVendNext upgrade", "live": True},
                     {"what": "a sandbox copy for your sandbox shop, in the same order at the same price", "live": True}]
SKIP = re.compile(r"(^|/)(\.[^/]*|__pycache__)(/|$)|\.pyc$")
IMAGE = re.compile(r"(?P<repo>[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+):(?P<tag>[A-Za-z0-9._-]+)")


def is_function(m: dict) -> bool:
    return m.get("runs") == "function"


def package_files(m: dict, root) -> list[tuple[str, pathlib.Path]]:
    """(name in the zip, file) for every file under the ``package`` paths, sorted; dot-files and caches left out."""
    root, out = pathlib.Path(root), []
    for part in m.get("package") or []:
        p = root / part
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else []
        out += [(f.relative_to(root).as_posix(), f) for f in files if not SKIP.search(f.relative_to(root).as_posix())]
    return sorted(set(out))


def write_zip(m: dict, root, out) -> str:
    """Write the function's package, the same bytes for the same files (fixed dates and modes); its sha256."""
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, f in package_files(m, root):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr, info.compress_type, info.create_system = 0o644 << 16, zipfile.ZIP_DEFLATED, 3
            z.writestr(info, f.read_bytes())
    return hashlib.sha256(pathlib.Path(out).read_bytes()).hexdigest()


def check(folder, image: str, plan: str, partner: str, env: str, customer: str = "",
          root=None) -> tuple[list[str], dict]:
    """Return (refusals, the app's settings). An empty list means the service would host it."""
    bad = validate_app.check_folder(folder) + licence.check(folder, hosted=True)
    try:
        m = json.loads((pathlib.Path(folder) / "app.json").read_text("utf-8"))
    except (OSError, ValueError):
        return bad, {}
    if not isinstance(m, dict):
        return bad, {}
    name, version = m.get("app"), m.get("version")
    if env not in PLANS["envs"]:
        bad.append(f"env: one of {', '.join(PLANS['envs'])}")
    if plan not in PLANS["plans"]:
        bad.append(f"plan: one of {', '.join(PLANS['plans'])}")
    else:
        enforced = PLANS["plans"][plan]["enforced"]
        if isinstance(m.get("size"), str) and m["size"] in PLANS["sizes"] and m["size"] not in enforced["sizes"]:
            bad.append(f"size: {m['size']} is not on the {plan} plan (it allows {', '.join(enforced['sizes'])})")
        if env in PLANS["envs"] and env not in enforced["envs"]:
            bad.append(f"env: a {env} copy is not on the {plan} plan (it allows {', '.join(enforced['envs'])})")
    if not SLUG.fullmatch(partner or ""):
        bad.append("partner: 2 to 31 lower-case letters, digits and hyphens, starting with a letter")
    if customer and not SLUG.fullmatch(customer):
        bad.append("customer: 2 to 31 lower-case letters, digits and hyphens, starting with a letter")
    if isinstance(name, str):
        if name.endswith("-"):
            bad.append("app: the name cannot end with a hyphen (it becomes part of an address)")
        if name in PLANS["reserved_names"]:
            bad.append(f"app: {name!r} is reserved; choose another name")
        if any(name.endswith("-" + e) for e in PLANS["envs"]):
            bad.append(f"app: a name ending in an environment's name ({', '.join(PLANS['envs'])}) would take another app's address")
        if env != "prod" and len(f"{name}-{env}") > 40:
            bad.append(f"app: {name}-{env} is longer than 40 characters")
    if isinstance(m.get("region"), str) and m["region"] not in PLANS["regions"]:
        bad.append(f"region: {m['region']!r} is not served yet; we serve {', '.join(PLANS['regions'])}. " + PLANS["regions_on_request"])
    if is_function(m):
        if image:
            bad.append("image: a function is not an image; give --zip (its package) instead")
        root = pathlib.Path(root or folder)
        for part in m.get("package") or []:
            if isinstance(part, str) and not (root / part).exists():
                bad.append(f"package: {part} is not in {root} (give --root: the folder the package paths start from)")
        handler = m.get("handler") if isinstance(m.get("handler"), str) else ""
        if handler and "/" + handler.rsplit(".", 1)[0] + ".py" not in ["/" + n for n, _ in package_files(m, root)]:
            bad.append(f"handler: {handler.rsplit('.', 1)[0]}.py is not in the package")
        return bad, m
    im = IMAGE.fullmatch(image or "")
    if not im:
        bad.append("image: <registry>/<repository>:<version>")
    elif im["tag"] != version:
        bad.append(f"image: the tag must be the app's version from app.json ({version}), never 'latest' or another name, "
                   "so what runs is what the settings file says")
    return bad, m


def module_label(m: dict, env: str) -> str:
    return "app_" + re.sub(r"[^a-z0-9]", "_", m["app"] if env == "prod" else f"{m['app']}_{env}")


def describe(m: dict, image: str, plan: str, partner: str, env: str, customer: str = "", package: str = "") -> dict:
    """What the service would create for this app (no prices)."""
    if is_function(m):
        return describe_function(m, plan, partner, env, customer, package)
    p, size = PLANS["plans"][plan], PLANS["sizes"][m["size"]]
    ident = m["app"] if env == "prod" else f"{m['app']}-{env}"
    env_vars = m.get("env", [])
    secrets = [e["name"] for e in env_vars if e.get("secret") and e.get("required")]
    later = [e["name"] for e in env_vars if e.get("secret") and not e.get("required")]
    plain = [e["name"] for e in env_vars if not e.get("secret")]
    return {
        "address": f"https://{ident}.{PLANS['domain']}",
        "app": ident, "partner": partner, "customer": customer or None, "plan": plan, "env": env,
        "image": image, "region": PLANS["regions"][m["region"]],
        "size": {"name": m["size"], "vcpu": size["vcpu"], "memory_mb": size["memory_mb"], "cpu_architecture": "ARM64"},
        "enforced": p["enforced"],
        "includes": p["includes"],
        "secrets_to_supply": secrets,
        "secrets_added_when_used": later,
        "settings_to_supply": plain,
        "creates": [
            f"an image registry partner-apps/{ident} (versions cannot be overwritten; the newest 10 kept)",
            *[f"a secret partner-apps/{ident}/{s} (its value is put in by the service, never shown)" for s in secrets],
            f"{p['enforced']['instances']} always-on container(s), {size['vcpu']} vCPU and {size['memory_mb']} MB each, "
            f"health check GET {m['health']}, restarted when it fails",
            f"logs kept {p['enforced']['log_days']} days",
            f"a firewall rule: in only from our load balancer on port {m['port']}, out only HTTPS",
            f"the address https://{ident}.{PLANS['domain']} (certificate included)",
            *([f"a shops table for the shops that connect to the app, encrypted at rest, readable and writable by this "
               f"app's containers alone (IVN_SHOPS_TABLE)"] if m.get("shops") else []),
        ],
        "infrastructure_block": block(m, plan, partner, env, secrets, image, plain, customer),
        "put_live": [
            f"tofu apply -exclude=module.{module_label(m, env)}.aws_ecs_service.this",
            "copy the image into the app's registry with its version tag, and put each secret's value",
            "tofu apply   (only the service is left to create)",
        ],
    }


def describe_function(m: dict, plan: str, partner: str, env: str, customer: str, package: str) -> dict:
    """A press-only app: a function paid per call behind the shared load balancer, no container (chapter 14b)."""
    p = PLANS["plans"][plan]
    ident = m["app"] if env == "prod" else f"{m['app']}-{env}"
    plain = [e["name"] for e in m.get("env", []) if not e.get("secret")]
    key = f"{ident}/{m['version']}.zip"
    return {
        "address": f"https://{ident}.{PLANS['domain']}",
        "app": ident, "partner": partner, "customer": customer or None, "plan": plan, "env": env, "runs": "function",
        "package": package or None, "region": PLANS["regions"][m["region"]], "schedule": m.get("schedule") or {},
        "size": {"name": m["size"], "memory_mb": FUNCTION_MB, "cpu_architecture": "ARM64"},
        "enforced": p["enforced"], "includes": FUNCTION_INCLUDES,
        "secrets_to_supply": [], "secrets_added_when_used": [], "settings_to_supply": plain,
        "creates": [
            f"a function {ident}, {FUNCTION_MB} MB, ARM64, run only when called (paid per call), "
            f"handler {m['handler']}, its code the package {key}, each call at most {m.get('timeout', 10)} seconds",
            *[f"a schedule {n}: the function runs {w} (UTC), with a role that may call this function and nothing else"
              for n, w in sorted((m.get("schedule") or {}).items())],
            f"logs kept {p['enforced']['log_days']} days",
            f"a shops table for the shops that connect to the app, encrypted at rest, readable and writable by this "
            f"function alone (IVN_SHOPS_TABLE)",
            f"the address https://{ident}.{PLANS['domain']} on the shared load balancer (certificate included)",
        ],
        "infrastructure_block": function_block(m, plan, partner, env, plain, customer),
        "put_live": [
            "the hosting's code bucket exists (for the first function: apply it alone first, "
            "tofu apply with -target for aws_s3_bucket.code and each of its settings)",
            f"copy the package into the code bucket as {key}, never over an existing name "
            "(the bucket refuses a write without If-None-Match: *)",
            "tofu apply",
        ],
    }


def function_block(m: dict, plan: str, partner: str, env: str, plain: list[str], customer: str) -> str:
    """The function's module block for the infrastructure repository's foundation/apps.tf."""
    extra = f'  customer    = "{customer}"\n' if customer else ""
    extra += f"  timeout     = {m['timeout']}\n" if "timeout" in m else ""
    if m.get("schedule"):
        extra += "  schedule    = { " + ", ".join(f"{n} = {json.dumps(w)}" for n, w in sorted(m["schedule"].items())) + " }\n"
    extra += f"  # plain settings to supply in plain_env: {', '.join(plain)}\n" if plain else ""
    return (f'module "{module_label(m, env)}" {{\n'
            f'  source      = "../modules/function"\n'
            f'  name        = "{m["app"]}"\n'
            f'  partner     = "{partner}"\n'
            f'  plan        = "{plan}"\n'
            f'  env         = "{env}"\n'
            f'  size        = "{m["size"]}"\n'
            f'  app_version = "{m["version"]}"\n'
            f'  handler     = "{m["handler"]}"\n'
            f'{extra}'
            f'  code_bucket = local.code_bucket\n'
            f'  platform    = local.platform\n'
            f'}}\n')


def block(m: dict, plan: str, partner: str, env: str, secrets: list[str], image: str, plain: list[str], customer: str) -> str:
    """The module block the service pastes into the infrastructure repository's foundation/apps.tf."""
    names = ", ".join(json.dumps(s) for s in secrets)
    extra = f'  customer     = "{customer}"\n' if customer else ""
    extra += "  shops        = true\n" if m.get("shops") else ""
    extra += f"  # plain settings to supply in plain_env: {', '.join(plain)}\n" if plain else ""
    return (f'module "{module_label(m, env)}" {{\n'
            f'  source       = "../modules/app"\n'
            f'  name         = "{m["app"]}"\n'
            f'  partner      = "{partner}"\n'
            f'  plan         = "{plan}"\n'
            f'  env          = "{env}"\n'
            f'  size         = "{m["size"]}"\n'
            f'  image_tag    = "{image.rsplit(":", 1)[1]}"\n'
            f'  port         = {m["port"]}\n'
            f'  health       = "{m["health"]}"\n'
            f'  secret_names = [{names}]\n'
            f'{extra}'
            f'  platform     = local.platform\n'
            f'}}\n')


ORDER_COMMANDS = ("order", "status", "secret", "cancel")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ORDER_COMMANDS:
        import hosting_order  # noqa: PLC0415  (only an order needs the signing key)
        return hosting_order.main(argv)
    ap = argparse.ArgumentParser(description="Plan an app for CitiXsys App Hosting (this changes nothing). To order it "
                                             "online: deploy_app.py order <folder> … (guide 14b).")
    ap.add_argument("folder", help="the app's folder: app.json and Dockerfile")
    ap.add_argument("--image", default="", help="a container: <registry>/<repository>:<version>, the version from app.json")
    ap.add_argument("--zip", default="", help="a function (app.json \"runs\": \"function\"): where to write its package")
    ap.add_argument("--root", default="", help="a function: the folder its package paths start from (default: the app's)")
    ap.add_argument("--plan", required=True, help=", ".join(PLANS["plans"]))
    ap.add_argument("--partner", required=True, help="your partner name, lower case, e.g. acme")
    ap.add_argument("--env", default="prod", help=", ".join(PLANS["envs"]))
    ap.add_argument("--customer", default="", help="for an app built for one customer: its short name (a tag on the costs)")
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    bad, m = check(a.folder, a.image, a.plan, a.partner, a.env, a.customer, a.root or None)
    if not bad and is_function(m) and not a.zip:
        bad.append("zip: a function needs --zip, the file this tool writes its package to")
    if not bad and not is_function(m) and not a.image:
        bad.append("image: <registry>/<repository>:<version>")
    if bad:
        for b in bad:
            print("REFUSED: " + b)
        print(f"{len(bad)} refusal(s); nothing planned")
        return 1
    package = ""
    if is_function(m):
        package = f"{a.zip} (sha256 {write_zip(m, a.root or a.folder, a.zip)})"
    d = describe(m, a.image, a.plan, a.partner, a.env, a.customer, package)
    if a.json:
        print(json.dumps(d, indent=1))
        return 0
    who = d["partner"] + (f" (customer {d['customer']})" if d["customer"] else "")
    print(f"PLANNED: {d['app']} for {who}, plan {d['plan']}, {d['env']}")
    print(f"  address  {d['address']}")
    if d.get("runs") == "function":
        print(f"  package  {d['package']}")
        print(f"  size     a function of {d['size']['memory_mb']} MB, ARM64, region {d['region']}, run only when called"
              + (" or on its schedule" if d.get("schedule") else ""))
    else:
        print(f"  image    {d['image']}")
        print(f"  size     {d['size']['name']}: {d['size']['vcpu']} vCPU, {d['size']['memory_mb']} MB, ARM64, region {d['region']}")
    print("  creates:")
    for c in d["creates"]:
        print(f"    - {c}")
    print("  the plan includes:")
    for i in d["includes"]:
        print(f"    - {i['what']}" + ("" if i["live"] else " (not offered yet)"))
    if d["secrets_to_supply"]:
        print(f"  secrets the service asks you for (never in a file): {', '.join(d['secrets_to_supply'])}")
    if d["secrets_added_when_used"]:
        print(f"  added when you need them: {', '.join(d['secrets_added_when_used'])}")
    if d["settings_to_supply"]:
        print(f"  settings the service asks you for: {', '.join(d['settings_to_supply'])}")
    print("\nNothing was changed. To order it online and have it built with no person: deploy_app.py order "
          f"{a.folder} --plan {d['plan']} --partner {d['partner']} --github <owner>/<repo> --accept-schedule (guide 14b).\n"
          "For an app put live by hand instead, CitiXsys adds this to the hosting infrastructure after review:\n")
    print(d["infrastructure_block"])
    print("and puts it live in this order:" if d.get("runs") == "function" else
          "and puts it live in this order (the service cannot start before its image and secrets exist):")
    for i, step in enumerate(d["put_live"], 1):
        print(f"  {i}. {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
