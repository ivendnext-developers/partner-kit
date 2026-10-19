"""Laptop tests of S12's gate script (release_gate.sh) and its recorder, no bench: a stub `docker` and a stub console stand in for the
staging shop, so the script's own logic — what it prints, and what it exits — is tested on its own. The real run is on our test bench (its own driver, not in the kit).

    python3 -m unittest discover -s samples/s12_release_gate/tests -p 'test_*.py'
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
S12 = HERE.parent
GATE = S12 / "release_gate.sh"
ROOT = S12.parents[1]

BASKETS = {"baskets": [{"name": "one", "lines": [["A", 1, None]], "expect": {"grand_total": 10.0, "tax": 1.0}},
                       {"name": "two", "lines": [["B", 2, None]], "expect": {"grand_total": 20.0, "tax": 2.0}}]}


def rec(rows, open_days=None, ok=True):
    out = {"ok": ok, "gate": rows, "gate_green": bool(rows) and all(r["state"] == "matched" for r in rows),
           "open_days": [] if open_days is None else open_days}
    return out


def row(i, name, state="matched", exp=10.0, booked=10.0, preview=10.0, detail=None):
    return {"id": f"G{i:03d}", "name": name, "state": state, "detail": detail or [], "expect": {"grand_total": exp, "tax": 1.0},
            "preview": {"grand_total": preview}, "booked": {"grand_total": booked, "tax": 1.0}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "bin").mkdir()
        # a stub docker: `docker cp` succeeds unless the container is the one that does not exist
        (self.tmp / "bin" / "docker").write_text('#!/bin/bash\n[ "$1" = cp ] && [[ "$3" != no-such-bench:* ]] && exit 0\nexit 1\n')
        (self.tmp / "console.sh").write_text('#!/bin/bash\n# <script> <out> <steps…>: leave the run record the test prepared\n'
                                             '[ -n "$ARGS_LOG" ] && printf "%s\\n" "$@" > "$ARGS_LOG"\n'
                                             'cp "$FAKE_REC" "$GATE_RUNS/$2.json" 2>/dev/null; exit 0\n')
        for f in (self.tmp / "bin" / "docker", self.tmp / "console.sh"):
            f.chmod(0o755)
        (self.tmp / "runs").mkdir()
        self.baskets = self.tmp / "baskets.json"
        self.baskets.write_text(json.dumps(BASKETS))

    def run_gate(self, record=None, args=None, env=None):
        if record is not None:
            (self.tmp / "rec.json").write_text(json.dumps(record))
        e = dict(os.environ, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}", GATE_CONSOLE=f"bash {self.tmp / 'console.sh'}",
                 GATE_RUNS=str(self.tmp / "runs"), GATE_CONTAINER="staging-shop-1", FAKE_REC=str(self.tmp / "rec.json"),
                 GATE_KIT_ROOT=str(ROOT))
        e.update(env or {})
        r = subprocess.run(["bash", str(GATE), *(args or ["--baskets", str(self.baskets)])], capture_output=True, text=True, env=e)
        return r.returncode, r.stdout + r.stderr

    def test_all_green_exits_zero_and_prints_a_line_per_basket_with_the_three_figures(self):
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two", exp=20.0, booked=20.0, preview=20.0)]))
        self.assertEqual(rc, 0, out)
        self.assertIn("GATE RESULT GREEN", out)
        self.assertIn('GATE   G001 OK  "one"  expected 10.00  booked 10.00  preview 10.00', out)
        self.assertIn('GATE   G002 OK  "two"  expected 20.00  booked 20.00  preview 20.00', out)

    def test_a_basket_off_from_its_recorded_answer_is_red_named_with_both_figures(self):
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two", state="diverged", exp=20.0, booked=19.0, preview=19.0,
                                                          detail=["grand_total: recorded answer 20.00, booked 19.00"])]))
        self.assertEqual(rc, 1)
        self.assertIn("GATE RESULT RED", out)
        self.assertIn('G002 RED "two"  expected 20.00  booked 19.00', out)
        self.assertIn("recorded answer 20.00, booked 19.00", out)
        self.assertIn('G001 OK  "one"', out)

    def test_a_day_left_open_makes_it_red_even_when_every_basket_matched(self):
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two")], open_days=["POS-OPEN-1"]))
        self.assertEqual(rc, 1)
        self.assertIn("GATE open POS days: 1 RED", out)

    def test_an_unknown_open_day_count_is_not_green(self):
        r = rec([row(1, "one"), row(2, "two")])
        r.pop("open_days")
        rc, out = self.run_gate(r)
        self.assertEqual(rc, 1)
        self.assertIn("open POS days: unknown RED", out)

    def test_a_red_self_check_makes_it_red(self):
        sys.path.insert(0, str(ROOT / "tools" / "selfcheck"))
        from selftest import PLANTS                                   # the self-check's own money plant: the trap's shape
        files = next(f for k, _, f, *_ in PLANTS if k == "server_money")
        bad = self.tmp / "money_app"
        for rel, body in files.items():
            (bad / rel).parent.mkdir(parents=True, exist_ok=True)
            (bad / rel).write_text(body)
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two")]), ["--baskets", str(self.baskets), "--app", str(bad)])
        self.assertEqual(rc, 1)
        self.assertIn("GATE self-check RED", out)
        self.assertIn("writes `rate`", out, "red for the money rule, not for a missing app")
        self.assertIn("GATE baskets GREEN", out, "the other stages still ran and are shown")

    def test_a_clean_app_passes_the_self_check(self):
        sys.path.insert(0, str(ROOT / "tools" / "selfcheck"))
        from selftest import CLEAN                                    # the self-check's own clean app
        ok = self.tmp / "clean_app"
        for rel, body in CLEAN.items():
            (ok / rel).parent.mkdir(parents=True, exist_ok=True)
            (ok / rel).write_text(body)
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two")]), ["--baskets", str(self.baskets), "--app", str(ok)])
        self.assertEqual(rc, 0, out)
        self.assertIn("GATE self-check GREEN", out)

    def test_it_cannot_run_is_exit_two_never_a_pass(self):
        rc, out = self.run_gate(None)                                      # the console leaves no record
        self.assertEqual(rc, 2)
        self.assertIn("nothing is proven", out)
        rc, out = self.run_gate(rec([]), env={"GATE_CONTAINER": "no-such-bench"})
        self.assertEqual(rc, 2)
        self.assertIn("could not copy the baskets", out)
        bad = self.tmp / "bad.json"
        bad.write_text('{"baskets": [{"name": "x"}]}')
        self.assertEqual(self.run_gate(rec([]), ["--baskets", str(bad)])[0], 2)
        self.assertEqual(self.run_gate(rec([]), ["--baskets", str(self.tmp / "none.json")])[0], 2)
        self.assertEqual(self.run_gate(rec([]), ["--nonsense"])[0], 2)
        rc, out = subprocess.run(["bash", str(GATE), "--baskets"], capture_output=True, text=True, timeout=20, env=dict(os.environ, GATE_CONSOLE="true", GATE_RUNS="/x", GATE_CONTAINER="x")), ""
        self.assertEqual(rc.returncode, 2, "a flag with no value ends at once with exit 2 (it used to loop for ever)")
        e = {k: v for k, v in os.environ.items() if k not in ("GATE_CONSOLE", "GATE_RUNS", "GATE_CONTAINER")}
        r = subprocess.run(["bash", str(GATE), "--baskets", str(self.baskets)], capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 2, "no staging box named: could not run, not red")
        rc, out = self.run_gate(rec([], ok=False) | {"error": "boom"})
        self.assertEqual(rc, 2, "a console step that failed before any basket is not a pass")

    def test_a_basket_with_no_recorded_answer_cannot_pass_silently(self):
        nob = {"baskets": [BASKETS["baskets"][0], {"name": "no answer", "lines": [["B", 1, None]]},
                           {"name": "misspelled", "lines": [["C", 1, None]], "expected": {"grand_total": 5.0}}]}
        p = self.tmp / "noexpect.json"
        p.write_text(json.dumps(nob))
        rc, out = self.run_gate(rec([row(1, "one")]), ["--baskets", str(p)])
        self.assertEqual(rc, 2, out)
        self.assertIn("no answer; misspelled", out)
        rc, out = self.run_gate(rec([row(1, "one")]), ["--baskets", str(p), "--record"])
        self.assertEqual(rc, 0, "the one recording run is allowed without answers")

    def test_the_put_and_remove_commands_are_the_customers_to_set(self):
        (self.tmp / "put.sh").write_text('#!/bin/bash\necho "$@" >> "$GATE_LOG"\n'); (self.tmp / "put.sh").chmod(0o755)
        (self.tmp / "rm.sh").write_text('#!/bin/bash\necho "rm $@" >> "$GATE_LOG"\n'); (self.tmp / "rm.sh").chmod(0o755)
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two", exp=20.0, booked=20.0, preview=20.0)]),
                                env={"GATE_PUT": f"bash {self.tmp / 'put.sh'}", "GATE_RM": f"bash {self.tmp / 'rm.sh'}", "GATE_LOG": str(self.tmp / "log.txt")})
        self.assertEqual(rc, 0, out)
        log = (self.tmp / "log.txt").read_text()
        self.assertIn("baskets.json", log)
        self.assertIn("rm /home/frappe/pp_gate_", log)

    def test_the_kit_settings_reach_the_console_before_the_gate_steps(self):
        log = self.tmp / "args.txt"
        rc, out = self.run_gate(rec([row(1, "one"), row(2, "two", exp=20.0, booked=20.0, preview=20.0)]),
                                env={"ARGS_LOG": str(log), "GATE_KIT_SETTINGS": "kit_dir:/k;shop:/k/My Shop.json;record:/r/out.json"})
        self.assertEqual(rc, 0, out)
        args = log.read_text().splitlines()
        self.assertEqual(args[0], "tools/moneykit/kit.py", "the kit's own layout is the default script")
        self.assertEqual(args[2:5], ["kit_dir:/k", "shop:/k/My Shop.json", "record:/r/out.json"], "one step each, spaces kept")
        self.assertTrue(args[5].startswith("gate_stock:/home/frappe/pp_gate_") and args[6].startswith("gate:"), args)
        self.assertEqual(args[7:], ["pos_day_check"])
        rc, out = self.run_gate(rec([row(1, "one")]), env={"ARGS_LOG": str(log), "GATE_BENCH_TMP": "/srv/tmp"})
        self.assertTrue(log.read_text().splitlines()[2].startswith("gate_stock:/srv/tmp/pp_gate_"), "no setting: the gate steps come first")

    def test_a_kit_setting_that_could_ring_or_seed_is_refused(self):
        for bad in ("kit_dir:/k;run:baseline", "seed", "shop:"):
            rc, out = self.run_gate(rec([row(1, "one")]), env={"GATE_KIT_SETTINGS": bad})
            self.assertEqual(rc, 2, (bad, out))
            self.assertIn("takes only kit_dir:, shop: and record:", out)

    def test_no_baskets_rung_is_not_a_pass(self):
        rc, out = self.run_gate(rec([]))
        self.assertEqual(rc, 2, out)
        self.assertIn("no basket was rung", out)

    def test_record_expect_fills_the_answers_from_a_clean_run_only(self):
        src = {"baskets": [{"name": "one", "lines": [["A", 1, None]]}, {"name": "two", "lines": [["B", 2, None]]}]}
        (self.tmp / "src.json").write_text(json.dumps(src))
        (self.tmp / "run.json").write_text(json.dumps(rec([row(1, "one", booked=12.345), row(2, "two", booked=20.0)])))
        r = subprocess.run([sys.executable, str(S12 / "record_expect.py"), str(self.tmp / "src.json"), str(self.tmp / "run.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["baskets"][0]["expect"], {"grand_total": 12.35, "tax": 1.0})
        (self.tmp / "run.json").write_text(json.dumps(rec([row(1, "one"), row(2, "two", state="diverged")])))
        r = subprocess.run([sys.executable, str(S12 / "record_expect.py"), str(self.tmp / "src.json"), str(self.tmp / "run.json")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "a basket that did not match is never recorded")
        (self.tmp / "run.json").write_text(json.dumps(rec([row(1, "two"), row(2, "one")])))
        r = subprocess.run([sys.executable, str(S12 / "record_expect.py"), str(self.tmp / "src.json"), str(self.tmp / "run.json")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "answers are never paired with another basket's name")
        self.assertIn("not the same", r.stderr)


if __name__ == "__main__":
    unittest.main()
