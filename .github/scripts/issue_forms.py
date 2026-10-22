#!/usr/bin/env python3
"""The six feedback forms (feedback/*.md) as GitHub issue forms (.github/ISSUE_TEMPLATE/), generated so the two can
never drift apart. Edit the Markdown form, then run this from the repository's root:

    python3 .github/scripts/issue_forms.py            # rewrite the issue forms
    python3 .github/scripts/issue_forms.py --check    # exit 1 if an issue form differs from its Markdown form,
                                                      # or a form is over the cap (see CAPS)

The forms are filed in the private repository ivendnext-developers/partner-feedback, not here. After a change, copy the
seven generated files (the six forms and config.yml) from .github/ISSUE_TEMPLATE/ into that repository's
.github/ISSUE_TEMPLATE/ unchanged, and compare them byte for byte.

A form in the Markdown file is the fenced block under "The form". In it: a line "Label: <a | b>" is a required drop-down, and "Label: <hint>" a required one-line box;
"## n. Question" is a text box, required unless the heading ends "(optional)"; "- [ ] Text" is an optional tick box.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / ".github" / "ISSUE_TEMPLATE"
KIT_URL = "https://github.com/ivendnext-developers/partner-kit"
PARTNER_FORM = "https://www.ivendnext.com/partner/#be-a-partner"
FORMS = ("kit_defect", "point_request", "recipe_or_document_gap", "sample_request", "app_listing",
         "claim_a_need")
TICK_GROUP = {"app_listing": "The listing bar"}  # a tick box's group label; every other form's is "Money or the till"
CAPS = {"fields": 5, "required": 3}      # a form with more fields, or more required fields, than this is too long to fill in


def header(src: str) -> str:
    return f"# Generated from {src} by .github/scripts/issue_forms.py: edit that form, then re-run the script."


def parse(md: str) -> tuple[str, str, str, list[dict]]:
    """name, about, issue title and the form's fields, in order."""
    name, _, about = md.split("\n", 1)[0].lstrip("# ").partition(" — ")
    block = re.search(r"```markdown\n(.*?)\n```", md, re.S).group(1).split("\n")
    title = block[0].lstrip("# ").split("<")[0]
    fields: list[dict] = []
    for i, line in enumerate(block[1:], 1):
        m = re.match(r"^## (\d+)\. (.+?)( \(optional\))?$", line)
        if m:
            hint = "\n".join(block[i + 1:]).split("\n\n")[0].strip()
            hint = hint.removeprefix("<").removesuffix(">") if hint.count("<") == 1 else hint
            fields.append({"kind": "text", "id": f"s{m.group(1)}", "label": f"{m.group(1)}. {m.group(2)}",
                           "hint": hint, "required": not m.group(3)})
            continue
        m = re.match(r"^- \[ \] (.+)$", line)
        if m:
            fields.append({"kind": "tick", "id": f"tick_{len(fields) + 1}", "label": m.group(1), "required": False})
            continue
        m = None if fields else re.match(r"^([A-Z][A-Za-z /]+): <(.+)>$", line)
        if m:
            label, hint = m.group(1), m.group(2)
            opts = [o.strip() for o in hint.split("|")]
            fid = re.sub(r"[^a-z]+", "_", label.lower()).strip("_")
            if len(opts) > 1 and all(len(o.split()) <= 4 and "—" not in o for o in opts):
                fields.append({"kind": "drop", "id": fid, "label": label, "options": opts, "required": True})
            else:
                fields.append({"kind": "input", "id": fid, "label": label, "hint": hint, "required": True})
    return name, about, title, fields


def cap_problems(form: str, md: str) -> list[str]:
    fields = parse(md)[3]
    required = sum(f["required"] for f in fields)
    bad = []
    if len(fields) > CAPS["fields"]:
        bad.append(f"{form}: {len(fields)} fields, the most a form may have is {CAPS['fields']}")
    ids = [f["id"] for f in fields]
    if len(set(ids)) != len(ids):
        bad.append(f"{form}: two fields share an id, which GitHub rejects")
    if required > CAPS["required"]:
        bad.append(f"{form}: {required} required fields, the most a form may have is {CAPS['required']}")
    return bad


def form_yaml(form: str, md: str | None = None) -> str:
    q, src = json.dumps, f"feedback/{form}.md"
    name, about, title, fields = parse(md if md is not None else (ROOT / src).read_text("utf-8"))
    y = [header(src), f"name: {q(name)}", f"description: {q(about)}", f"title: {q(title)}",
         "body:", "  - type: markdown", "    attributes:",
         "      value: " + q("**Every member of the programme can read this issue**, other partners' and other customers' teams "
                             "too. Never put a secret in it (no key, password, signing secret or token), no shoppers' personal data, "
                             "and no customer's name unless the customer has agreed. "
                             f"What we may ask you next, and what happens after you send it: [`{src}`]({KIT_URL}/blob/main/{src}).")]
    for f in fields:
        if f["kind"] == "text":
            y += ["  - type: textarea", f"    id: {f['id']}", "    attributes:", f"      label: {q(f['label'])}",
                  f"      placeholder: {q(f['hint'])}", "    validations:", f"      required: {'true' if f['required'] else 'false'}"]
        elif f["kind"] == "tick":
            y += ["  - type: checkboxes", f"    id: {f['id']}", "    attributes:", f"      label: {q(TICK_GROUP.get(form, 'Money or the till'))}",
                  "      options:", f"        - label: {q(f['label'])}"]
        elif f["kind"] == "drop":
            y += ["  - type: dropdown", f"    id: {f['id']}", "    attributes:", f"      label: {q(f['label'])}",
                  "      options:", *[f"        - {q(o)}" for o in f["options"]], "    validations:", "      required: true"]
        else:
            y += ["  - type: input", f"    id: {f['id']}", "    attributes:", f"      label: {q(f['label'])}",
                  f"      placeholder: {q(f['hint'])}", "    validations:", "      required: true"]
    return "\n".join(y) + "\n"


def config_yaml() -> str:
    return (f"{header('feedback/README.md')}\nblank_issues_enabled: false\ncontact_links:\n"
            f"  - name: \"Not yet a member? Become an iVendNext Partner\"\n    url: \"{PARTNER_FORM}\"\n"
            "    about: \"These forms are for onboarded members. Everyone else starts with the iVendNext Partner form.\"\n")


def wanted() -> dict[str, str]:
    files = {f"{n}_{form}.yml": form_yaml(form) for n, form in enumerate(FORMS, 1)}
    files["config.yml"] = config_yaml()
    return files


def main() -> int:
    check = "--check" in sys.argv[1:]
    drift = []
    for name, text in wanted().items():
        f = OUT / name
        if check:
            if not f.exists() or f.read_text("utf-8") != text:
                drift.append(name)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, "utf-8")
    if check:
        long_ = [p for form in FORMS for p in cap_problems(form, (ROOT / f"feedback/{form}.md").read_text("utf-8"))]
        extra = sorted(p.name for p in OUT.glob("*") if p.name not in wanted())
        print("issue forms: " + ("match their Markdown forms" if not drift else "DIFFER: " + ", ".join(drift))
              + ("" if not long_ else "; TOO LONG: " + "; ".join(long_))
              + ("" if not extra else "; NOT GENERATED: " + ", ".join(extra)))
        return 1 if drift or long_ or extra else 0
    print(f"issue forms written: {len(FORMS)} forms + config.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
