import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger as L

DAY = "2026-01-12"


class LedgerTest(unittest.TestCase):
    def test_one_row_per_matter(self):
        rows = []
        a, new_a = L.add(rows, "Sign the dentist form", due="2026-01-16", thread="t-1", day=DAY)
        b, new_b = L.add(rows, "sign the DENTIST form!", day=DAY)           # the same words
        c, new_c = L.add(rows, "Form from the dentist", thread="t-1", day=DAY)  # the same mail thread
        self.assertTrue(new_a)
        self.assertFalse(new_b or new_c)
        self.assertEqual({a["id"], b["id"], c["id"]}, {"sign-the-dentist-form"})
        self.assertEqual(len(rows), 1)

    def test_a_closed_row_does_not_block_a_new_one(self):
        rows = []
        a, _ = L.add(rows, "Send the invoice", day=DAY)
        L.close(rows, a["id"], "sent", day=DAY)
        b, new = L.add(rows, "Send the invoice", day=DAY)
        self.assertTrue(new)
        self.assertNotEqual(a["id"], b["id"])

    def test_three_tiers_in_page_order(self):
        rows = []
        L.add(rows, "An idea", day=DAY)
        L.add(rows, "Later date", due="2026-02-01", day=DAY)
        L.add(rows, "Sooner date", due="2026-01-14", day=DAY)
        L.add(rows, "Blocks the talk", goal="speaking", blocks=True, day=DAY)
        got = [(r["title"], L.tier(r)) for r in L.open_rows(rows, DAY)]
        self.assertEqual(got, [("Blocks the talk", "blocks"), ("Sooner date", "dated"), ("Later date", "dated"), ("An idea", "wait")])

    def test_blocks_needs_a_goal(self):
        rows = []
        r, _ = L.add(rows, "No goal named", blocks=True, day=DAY)
        self.assertEqual(L.tier(r), "wait")

    def test_not_now_sleeps_until_its_day(self):
        rows = []
        r, _ = L.add(rows, "Renew the plan", day=DAY)
        L.sleep(rows, r["id"], "2026-01-19")
        self.assertEqual(L.open_rows(rows, "2026-01-18"), [])
        self.assertEqual(len(L.open_rows(rows, "2026-01-19")), 1)

    def test_verify_finds_what_is_wrong_with_the_list(self):
        rows = []
        L.add(rows, "Names no step", day="2026-01-01")
        late, _ = L.add(rows, "Past its date", needs="Pay it", due="2026-01-10", day="2026-01-11")
        L.check(rows, late["id"], "read the bill", day="2026-01-11")
        problems = {(b["id"], b["problem"]) for b in L.verify(rows, DAY)}
        self.assertIn(("names-no-step", "needs you, but names no step for you"), problems)
        self.assertIn(("names-no-step", "never re-checked against the live source"), problems)
        self.assertIn(("past-its-date", "past due since 2026-01-10"), problems)
        self.assertNotIn(("past-its-date", "never re-checked against the live source"), problems)

    def test_answers_are_written_by_script(self):
        rows = []
        a, _ = L.add(rows, "Approve the outline", needs="Say yes or no", day=DAY)
        b, _ = L.add(rows, "Renew the plan", needs="Say renew or cancel", day=DAY)
        unknown = L.apply_answers(rows, [{"id": a["id"], "answer": "yes"}, {"id": b["id"], "answer": "not_now"},
                                         {"id": "ghost", "answer": "yes"}, {"id": b["id"], "answer": "maybe"}], DAY)
        self.assertEqual(unknown, ["ghost", b["id"]])
        self.assertTrue(a["approved"])
        self.assertEqual((a["owner"], a["answered"]), ("agent", DAY))
        self.assertEqual((b["wake"], b["answered"]), ("2026-01-19", ""))

    def test_save_load_and_the_log(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data/ledger.json"
            rows = []
            L.add(rows, "One row", day=DAY)
            L.save(rows, p, event={"cmd": "add"})
            self.assertEqual(L.load(p), rows)
            self.assertEqual(json.loads(p.with_name("ledger-log.jsonl").read_text().strip()), {"cmd": "add"})
            self.assertEqual([x.name for x in p.parent.iterdir() if x.suffix == ".tmp"], [])

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["LEDGER"] = str(Path(d) / "ledger.json")
            try:
                self.assertEqual(L.main(["add", "Send the invoice", "--due", "2026-01-16", "--needs", "Press Send"]), 0)
                self.assertEqual(L.main(["add", "Send the invoice"]), 0)
                self.assertEqual(len(L.load()), 1)
                self.assertEqual(L.main(["done", "no-such-row"]), 2)
                self.assertEqual(L.main(["done", "send-the-invoice", "sent"]), 0)
                self.assertEqual(L.load()[0]["status"], "done")
            finally:
                del os.environ["LEDGER"]


if __name__ == "__main__":
    unittest.main()
