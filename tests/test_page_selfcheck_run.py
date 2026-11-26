import json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "rules"))
import build_page, ledger as L, run_morning, script_rules as S, selfcheck as C, slice_rules as R

DAY = "2026-01-12"  # a Monday


def rows():
    out = []
    L.add(out, "Idea <b>one</b>", needs="Decide", day=DAY)
    L.add(out, "Later date", needs="Do it", due="2026-02-01", day=DAY)
    L.add(out, "Sooner date", needs="Do it", due="2026-01-14", day=DAY)
    L.add(out, "Blocks the talk", needs="Say yes or no", goal="speaking", blocks=True, day=DAY)
    L.add(out, "Second blocker", needs="Say yes or no", goal="money", blocks=True, day=DAY)
    L.add(out, "Agent work", owner="agent", day=DAY)
    return out


class PageTest(unittest.TestCase):
    def test_three_decisions_at_most_top_tier_first(self):
        r = rows()
        asks = [{"id": x["id"], "question": x["title"] + "?"} for x in reversed(L.open_rows(r, DAY, "you"))]
        page = build_page.build(r, {"decisions": asks}, DAY)
        cards = page.split('<div class="card" data-id="')[1:]
        self.assertEqual([c.split('"')[0] for c in cards], ["blocks-the-talk", "second-blocker", "sooner-date"])
        self.assertEqual(S.page_test(page, r, DAY), [])  # the two that did not make the top 3 are still on the page

    def test_can_wait_is_folded_on_weekdays_and_open_on_friday(self):
        r = rows()
        monday, friday = build_page.build(r, {}, DAY), build_page.build(r, {}, "2026-01-16")
        self.assertIn("<details><summary>3. Can wait: 1 item(s), listed in full on Friday</summary>", monday)
        self.assertIn("<h2>3. Can wait</h2>", friday)
        self.assertNotIn("<details>", friday)
        self.assertLess(monday.index("1. Blocks a goal"), monday.index("2. Has a date"))
        self.assertLess(monday.index("Sooner date"), monday.index("Later date"))

    def test_text_is_escaped_and_agent_rows_stay_off(self):
        page = build_page.build(rows(), {"headline": "A <script> day"}, DAY)
        self.assertIn("Idea &lt;b&gt;one&lt;/b&gt;", page)
        self.assertIn("A &lt;script&gt; day", page)
        self.assertNotIn("Agent work", page)

    def test_ideas_only_on_friday(self):
        ask = {"ideas": ["one", "two", "three", "four"]}
        self.assertNotIn("New ideas", build_page.build(rows(), ask, DAY))
        friday = build_page.build(rows(), ask, "2026-01-16")
        self.assertIn("<li>three</li>", friday)
        self.assertNotIn("<li>four</li>", friday)


class SelfCheckTest(unittest.TestCase):
    def folder(self, d, r, page=True):
        f = Path(d) / DAY
        (f / "reports").mkdir(parents=True)
        for name in ("reads.json", "chief.json"):
            (f / name).write_text("{}")
        (f / "checked.json").write_text(json.dumps({"proposal": {"decisions": []}}))
        (f / "reports/mail.json").write_text(json.dumps({"read": {"mail": 3}}))
        if page:
            (f / "page.html").write_text(build_page.build(r, {}, DAY))
        return f

    def test_a_clean_run_has_no_faults(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            s = C.run_checks(C.Run(self.folder(d, r), DAY, r, ("mail",)))
            self.assertEqual((s["faults"], s["lines"]), (0, []))

    def test_a_missing_page_is_fixed_by_script(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            f = self.folder(d, r, page=False)
            s = C.run_checks(C.Run(f, DAY, r, ("mail",)))
            self.assertEqual((s["faults"], s["fixed"], s["filed"]), (1, 1, 0))
            self.assertEqual(S.page_test((f / "page.html").read_text(), r, DAY), [])

    def test_a_page_that_lost_an_item_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            f = self.folder(d, r)
            (f / "page.html").write_text((f / "page.html").read_text().replace('data-id="sooner-date"', ""))
            s = C.run_checks(C.Run(f, DAY, r, ("mail",)))
            self.assertEqual((s["faults"], s["fixed"]), (1, 1))

    def test_a_fault_no_script_can_fix_becomes_one_row_once(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            f = self.folder(d, r)
            (f / "reports/mail.json").write_text(json.dumps({"read": {"mail": 0}}))
            (f / "run.log").write_text("step 3\nTraceback (most recent call last):\n")
            saved = []
            first = C.run_checks(C.Run(f, DAY, r, ("mail",)), save=saved.append)
            again = C.run_checks(C.Run(f, DAY, r, ("mail",)), save=saved.append)
            self.assertEqual((first["faults"], first["filed"], again["filed"]), (2, 2, 0))
            self.assertEqual(len(saved), 1)
            filed = [x for x in r if x["id"].startswith("fault-")]
            self.assertEqual(len(filed), 2)
            self.assertTrue(all(x["owner"] == "agent" for x in filed))
            self.assertEqual(S.page_test(build_page.build(r, {}, DAY), r, DAY), [])

    def test_when_the_list_cannot_be_written_you_get_one_plain_line(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            f = self.folder(d, r)
            (f / "chief.json").write_text("{ not json")

            def broken(_):
                raise OSError("disk full")

            s = C.run_checks(C.Run(f, DAY, r, ("mail",)), save=broken)
            self.assertEqual((s["filed"], len(s["lines"])), (0, 1))

    def test_a_problem_on_the_list_is_said_not_filed(self):
        with tempfile.TemporaryDirectory() as d:
            r = rows()
            L.add(r, "Past its date", needs="Pay it", due="2026-01-02", day="2026-01-01")
            s = C.run_checks(C.Run(self.folder(d, r), DAY, r, ("mail",)))
            self.assertEqual((s["filed"], s["lines"]), (0, ["List row past-its-date: past due since 2026-01-02."]))


class RulesFileTest(unittest.TestCase):
    TEXT = "# title\n- [chief] before any section: ignored\n## Safety\n- [all] Never send.\n- [mail] Drafts only.\n" \
           "- [chief, check] Short lines.\n## Newer\n- Not tagged yet.\n"

    def test_each_agent_gets_only_its_slice(self):
        chief, mail = R.slice_for(self.TEXT, "chief"), R.slice_for(self.TEXT, "mail")
        self.assertIn("- Never send.", chief)
        self.assertIn("- Short lines.", chief)
        self.assertNotIn("Drafts only", chief)
        self.assertIn("- Drafts only.", mail)
        self.assertNotIn("Short lines", mail)
        self.assertNotIn("before any section", chief)

    def test_an_untagged_rule_reaches_every_agent(self):
        for agent in R.AGENTS:
            self.assertIn("- Not tagged yet. (not sorted yet: applies to every agent)", R.slice_for(self.TEXT, agent))

    def test_a_misspelled_tag_is_caught(self):
        self.assertEqual(R.unknown_tags("## A\n- [cheif, mail] x\n"), ["cheif"])

    def test_the_rules_file_in_this_kit_is_sound(self):
        text = (ROOT / "rules/RULES.md").read_text()
        self.assertEqual(R.unknown_tags(text), [])
        for agent in R.AGENTS:
            self.assertGreaterEqual(R.slice_for(text, agent).count("\n- "), 5)


class DemoRunTest(unittest.TestCase):
    def test_the_demo_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            lines = []
            res = run_morning.run(DAY, d, demo=True, ledger_path=Path(d) / "ledger.json", log=lines.append)
            page = res["page"].read_text()
            self.assertEqual(sorted({f["rule"] for f in res["findings"]}), [1, 2, 3, 4, 6, 7, 8])
            self.assertEqual(page.count('<div class="card"'), 3)
            self.assertIn("Say yes to the field trip on Thu Jan 22?", page)
            self.assertEqual(res["missing"], [])
            self.assertEqual((res["selfcheck"]["faults"], res["selfcheck"]["lines"]), (0, []))
            self.assertEqual(len(lines), 7 + len(res["findings"]))
            again = run_morning.run(DAY, d, demo=True, ledger_path=Path(d) / "ledger.json", log=lines.append)
            self.assertEqual(again["page"].read_text(), page)  # the same input gives the same page


if __name__ == "__main__":
    unittest.main()
