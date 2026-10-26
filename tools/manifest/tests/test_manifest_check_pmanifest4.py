# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_pmanifest4.py,
# at development b453a68eac6cc7e039f28a94f6f37147f151ec38; changed: the imports (the list of every-kind manifests, which the product names in its own module, is written here), the fixture folder, a note on how the file is copied (removed), and three print formats that read through the framework's name (now through the helper's own name: warned and refused either way).
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""A multi-select field, a settings record of the package's own (a single) and a notification's own print. Stdlib only.

The bench half (install, export, uninstall, update, the attachment itself): test_manifest_pmanifest4.py."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import validate as MC  # noqa: E402
from validate import validate  # noqa: E402

# the sample manifests that together hold every kind of extension (the product names them once, in its own module)
EVERY_KIND_FIXTURES = (
    "full_ok.json",
    "full_v2_ok.json",
    "kinds_v2_ok.json",
    "fiscal_v2_ok.json",
    "sample_s2_bins.json",
    "waveb_v2_ok.json",
    "waved_v2_ok.json",
    "listmark_v2_ok.json",
    "module_v2_ok.json",
    "register_v2_ok.json",
)

HERE = pathlib.Path(__file__).resolve().parent
RIGHTS = {r: 1 for r in MC.RIGHTS}
SETTINGS = "PP MF4 Settings"


def mf4() -> dict:
    """The lane's package: a multi-select of the package's own type and one of a shop type on Item, a plain table on
    Item, a settings record with a table, and a complaint whose notification attaches its own slip.
    """
    return {
        "manifest_version": 2,
        "app": "pp_mf4",
        "prefix": "PP MF4",
        "version": "0.1.0",
        "doctypes": [
            {
                "name": "PP MF4 Gender",
                "fields": [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
            },
            {
                "name": "PP MF4 Gender Pick",
                "istable": 1,
                "fields": [
                    {
                        "fieldname": "gender",
                        "fieldtype": "Link",
                        "label": "Gender",
                        "options": "PP MF4 Gender",
                        "in_list_view": 1,
                    }
                ],
            },
            {
                "name": "PP MF4 Brand Pick",
                "istable": 1,
                "fields": [
                    {
                        "fieldname": "brand",
                        "fieldtype": "Link",
                        "label": "Brand",
                        "options": "Brand",
                        "in_list_view": 1,
                    }
                ],
            },
            {
                "name": "PP MF4 Tag Row",
                "istable": 1,
                "fields": [{"fieldname": "note", "fieldtype": "Data", "label": "Note"}],
            },
            {
                "name": "PP MF4 Setting Row",
                "istable": 1,
                "fields": [{"fieldname": "note", "fieldtype": "Data", "label": "Note"}],
            },
            {
                "name": SETTINGS,
                "issingle": 1,
                "description": "Shelf-life and bypass settings",
                "track_changes": 1,
                "fields": [
                    {
                        "fieldname": "threshold_days",
                        "fieldtype": "Int",
                        "label": "Threshold (days)",
                    },
                    {
                        "fieldname": "bypass_role",
                        "fieldtype": "Link",
                        "label": "Bypass role",
                        "options": "Role",
                    },
                    {
                        "fieldname": "rows",
                        "fieldtype": "Table",
                        "label": "Rows",
                        "options": "PP MF4 Setting Row",
                    },
                ],
                "permissions": [{"role": "System Manager", **RIGHTS, "report": 0, "export": 0}],
            },
            {
                "name": "PP MF4 Complaint",
                "fields": [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
            },
        ],
        "custom_fields": [
            {
                "dt": "Item",
                "fieldname": "pp_mf4_genders",
                "fieldtype": "Table MultiSelect",
                "label": "Gender",
                "options": "PP MF4 Gender Pick",
            },
            {
                "dt": "Item",
                "fieldname": "pp_mf4_brands",
                "fieldtype": "Table MultiSelect",
                "label": "Brands",
                "options": "PP MF4 Brand Pick",
            },
            {
                "dt": "Item",
                "fieldname": "pp_mf4_tags",
                "fieldtype": "Table",
                "label": "Tags",
                "options": "PP MF4 Tag Row",
            },
        ],
        "property_setters": [
            {"doc_type": SETTINGS, "property": "description", "value": "Set once by the shop"},
            {"doc_type": SETTINGS, "field_name": "threshold_days", "property": "bold", "value": 1},
        ],
        "print_formats": [
            {
                "name": "PP MF4 Complaint Slip",
                "doc_type": "PP MF4 Complaint",
                "html": "<h3>{{ doc.title }}</h3>",
            }
        ],
        "notifications": [
            {
                "name": "PP MF4 Complaint Mail",
                "document_type": "PP MF4 Complaint",
                "event": "New",
                "channel": "Email",
                "subject": "Complaint {{ doc.title }}",
                "message": "A complaint was raised.",
                "recipients": [{"receiver_by_role": "System Manager"}],
                "attach_print": 1,
                "print_format": "PP MF4 Complaint Slip",
            }
        ],
        "workspaces": [
            {
                "name": "PP MF4 Space",
                "blocks": [{"type": "shortcut", "data": {"shortcut_name": "Settings", "col": 3}}],
                "shortcuts": [{"type": "DocType", "link_to": SETTINGS, "label": "Settings"}],
            }
        ],
    }


def dt(m: dict, name: str) -> dict:
    return next(d for d in m["doctypes"] if d["name"] == name)


def reasons(m: dict) -> str:
    return " | ".join(f"{x['where']}: {x['reason']}" for x in validate(m))


class TheLanesPackage(unittest.TestCase):
    def test_the_whole_package_passes(self):
        self.assertEqual(validate(mf4()), [])


class MultiSelect(unittest.TestCase):
    def test_a_multi_select_needs_an_own_child_type_with_a_link(self):
        m = mf4()
        dt(m, "PP MF4 Brand Pick")["fields"] = [
            {"fieldname": "note", "fieldtype": "Data", "label": "Note"}
        ]
        self.assertIn(
            "custom_fields[1]: a multi-select field points at one of the manifest's own child",
            reasons(m),
        )
        m = mf4()
        m["custom_fields"][0]["options"] = "Item Barcode"  # a shop's child type
        self.assertIn(
            "custom_fields[0]: a multi-select field points at one of the manifest's own child",
            reasons(m),
        )

    def test_its_link_is_shown_in_the_list_or_desk_drops_every_pick_on_save(self):
        m = mf4()
        dt(m, "PP MF4 Brand Pick")["fields"][0].pop("in_list_view")
        self.assertIn(
            "custom_fields[1]: a multi-select field points at one of the manifest's own child",
            reasons(m),
        )

    def test_on_the_packages_own_type_too(self):
        m = mf4()
        dt(m, "PP MF4 Complaint")["fields"].append(
            {
                "fieldname": "brands",
                "fieldtype": "Table MultiSelect",
                "label": "Brands",
                "options": "PP MF4 Tag Row",
            }
        )
        self.assertIn("doctypes[6].fields[1]: a multi-select field", reasons(m))


class SettingsRecord(unittest.TestCase):
    def test_it_carries_only_its_own_keys(self):
        for key, value in (
            ("autoname", "hash"),
            ("istable", 1),
            ("search_fields", "threshold_days"),
        ):
            with self.subTest(key=key):
                m = mf4()
                dt(m, SETTINGS)[key] = value
                self.assertIn("a settings record carries only", reasons(m))
        m = mf4()
        dt(m, SETTINGS)["issingle"] = 2
        self.assertIn("issingle is 0 or 1", reasons(m))

    def test_no_report_or_export_and_no_unique_or_search_index(self):
        for right in ("report", "export"):
            m = mf4()
            dt(m, SETTINGS)["permissions"][0][right] = 1
            self.assertIn("report and export are 0", reasons(m))
        for key in ("unique", "search_index"):
            m = mf4()
            dt(m, SETTINGS)["fields"][0][key] = 1
            self.assertIn(f"a settings record's field carries no '{key}'", reasons(m))

    def test_a_setter_never_makes_a_single_and_sets_no_more_than_the_single_may(self):
        m = mf4()
        m["property_setters"].append(
            {"doc_type": "PP MF4 Complaint", "property": "issingle", "value": 1}
        )
        self.assertIn("may not change 'issingle'", reasons(m))
        m = mf4()
        m["property_setters"].append(
            {"doc_type": SETTINGS, "property": "sort_field", "value": "threshold_days"}
        )
        self.assertIn(
            "on a settings record a property setter may set only description, track_changes",
            reasons(m),
        )
        m = mf4()
        m["property_setters"].append(
            {
                "doc_type": SETTINGS,
                "field_name": "threshold_days",
                "property": "unique",
                "value": 1,
            }
        )
        self.assertIn("may only change how the field is shown", reasons(m))
        m = mf4()
        m["property_setters"].append(
            {"doc_type": SETTINGS, "property": "track_changes", "value": 0}
        )
        self.assertEqual(validate(m), [])

    def test_a_shortcut_opens_its_form_and_nothing_else(self):
        m = mf4()
        m["workspaces"][0]["shortcuts"][0]["doc_view"] = "List"
        self.assertIn(f"workspaces[0]: '{SETTINGS}' {MC.SINGLE_REASON}", reasons(m))
        m = mf4()
        m["workspaces"][0]["shortcuts"][0]["doc_view"] = ""
        self.assertEqual(validate(m), [])

    def test_a_link_or_a_table_field_naming_it_is_refused(self):
        for ft, owner in (
            ("Link", "PP MF4 Complaint"),
            ("Table", "PP MF4 Complaint"),
            ("Table MultiSelect", "PP MF4 Complaint"),
        ):
            with self.subTest(ft=ft):
                m = mf4()
                dt(m, owner)["fields"].append(
                    {"fieldname": "s", "fieldtype": ft, "label": "S", "options": SETTINGS}
                )
                self.assertIn(f"doctypes[6]: '{SETTINGS}' {MC.SINGLE_REASON}", reasons(m))
        m = mf4()
        m["custom_fields"].append(
            {
                "dt": "Item",
                "fieldname": "pp_mf4_settings",
                "fieldtype": "Link",
                "label": "S",
                "options": SETTINGS,
            }
        )
        self.assertIn(f"custom_fields[3]: '{SETTINGS}' {MC.SINGLE_REASON}", reasons(m))


def _swap(x, names: set, to: str):
    """Every string naming one of ``names`` becomes ``to``; (the copy, how many)."""
    if isinstance(x, dict):
        out = {k: _swap(v, names, to) for k, v in x.items()}
        return {k: v[0] for k, v in out.items()}, sum(v[1] for v in out.values())
    if isinstance(x, list):
        out = [_swap(v, names, to) for v in x]
        return [v[0] for v in out], sum(v[1] for v in out)
    return (to, 1) if isinstance(x, str) and x in names else (x, 0)


class OnlyTheAllowListNamesIt(unittest.TestCase):
    def test_every_other_kind_naming_a_settings_record_is_refused(self):
        seen = set()
        for f in EVERY_KIND_FIXTURES:
            base = json.loads((HERE / "fixtures" / f).read_text())
            for kind in MC.KINDS:
                if (
                    kind in ("doctypes", "property_setters", "workspaces")
                    or not base.get(kind)
                    or kind in seen
                ):
                    continue
                with self.subTest(kind=kind, fixture=f):
                    m = copy.deepcopy(base)
                    single = f"{m['prefix']} Settings"
                    m.setdefault("doctypes", []).append(
                        {
                            "name": single,
                            "issingle": 1,
                            "fields": [{"fieldname": "x", "fieldtype": "Data"}],
                        }
                    )
                    # the negative control: the single alone draws no refusal at this kind
                    self.assertNotIn(MC.SINGLE_REASON, reasons(m))
                    names = {d["name"] for d in m["doctypes"] if not d.get("istable")} - {single}
                    names |= {"Customer", "Item", "POS Invoice", "Sales Invoice", "Batch"}
                    el, hit = _swap(m[kind][0], names, single)
                    if not hit:  # an element naming no record type: the name anywhere in it
                        key = next(k for k, v in el.items() if isinstance(v, str))
                        el[key] = single
                    m[kind][0] = el
                    self.assertIn(f"{kind}[0]: '{single}' {MC.SINGLE_REASON}", reasons(m))
                    seen.add(kind)
        self.assertEqual(seen, set(MC.KINDS) - {"doctypes", "property_setters", "workspaces"})

    def test_another_case_or_spacing_of_its_name_is_the_same_name(self):
        for spelling in ("pp mf4 settings", "PP MF4 Settings ", "PP  MF4 Settings"):
            with self.subTest(spelling=spelling):
                m = mf4()
                m["workspaces"][0]["shortcuts"][0].update(link_to=spelling, doc_view="List")
                self.assertIn(MC.SINGLE_REASON, reasons(m))

    def test_a_property_setter_and_a_shortcut_are_allowed(self):
        self.assertEqual(validate(mf4()), [])  # it carries both


class OwnPrint(unittest.TestCase):
    def note(self, m) -> dict:
        return m["notifications"][0]

    def test_refused_each_by_its_reason(self):
        cases = {
            "attach_files": lambda m: self.note(m).update(
                attach_files=[{"file": "/private/files/x.pdf"}]
            ),
            "from_attach_field": lambda m: self.note(m).update(from_attach_field="title"),
            "a shop's format": lambda m: self.note(m).update(print_format="Standard"),
            "a format of another record type": lambda m: (
                m["print_formats"].append(
                    {"name": "PP MF4 Gender Card", "doc_type": "PP MF4 Gender", "html": "x"}
                ),
                self.note(m).update(print_format="PP MF4 Gender Card"),
            ),
            "attach_print without a format": lambda m: self.note(m).pop("print_format"),
            # the manifest's own format FOR the shop's type: only the shop-type rule refuses it
            "either key on a shop's type": lambda m: (
                m["print_formats"].append(
                    {"name": "PP MF4 Batch Card", "doc_type": "Batch", "html": "{{ doc.name }}"}
                ),
                self.note(m).update(
                    document_type="Batch",
                    event="Days Before",
                    days_in_advance=3,
                    date_changed="expiry_date",
                    print_format="PP MF4 Batch Card",
                ),
            ),
            "a format including another template": lambda m: m["print_formats"][0].update(
                html='{% include "templates/discussions/discussions_section.html" %}'
            ),
            "a format including with a + marker": lambda m: m["print_formats"][0].update(
                html='{%+ include "templates/x.html" %}'
            ),
            "a format importing with a - marker": lambda m: m["print_formats"][0].update(
                html='{%- import "templates/x.html" as x %}'
            ),
            "a format extending another": lambda m: m["print_formats"][0].update(
                html='{% extends "templates/x.html" %}'
            ),
            "a format running a script": lambda m: m["print_formats"][0].update(
                html="{{ run_script('PP Script') }}"
            ),
            "a format using the framework": lambda m: m["print_formats"][0].update(
                html="{{ get_all('Customer') }}"
            ),
        }
        words = {
            "attach_files": MC.ATTACH_FILE_REASON,
            "from_attach_field": MC.ATTACH_FILE_REASON,
            "a format using the framework": MC.ATTACH_READER_REASON,
            "a format including another template": MC.ATTACH_READER_REASON,
            "a format including with a + marker": MC.ATTACH_READER_REASON,
            "a format importing with a - marker": MC.ATTACH_READER_REASON,
            "a format extending another": MC.ATTACH_READER_REASON,
            "a format running a script": MC.ATTACH_READER_REASON,
        }
        for case, change in cases.items():
            with self.subTest(case=case):
                m = mf4()
                change(m)
                self.assertIn(words.get(case, MC.ATTACH_PRINT_REASON), reasons(m))

    def test_the_same_format_unattached_is_only_warned(self):
        m = mf4()
        # in the shop, since 2.1.0, a row read of a type ivn_rows serves made through the framework's reader is refused
        # even unattached; Address is not one (the kit's copy reads the helper by its own name, which is only warned)
        m["print_formats"][0]["html"] = "{{ get_all('Address') }}"
        self.note(m).pop("attach_print")
        self.note(m).pop("print_format")
        self.assertEqual(validate(m), [])
        self.assertTrue(MC.warnings(m))


if __name__ == "__main__":
    unittest.main()
