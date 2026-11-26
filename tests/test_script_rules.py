import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_page, ledger as L, script_rules as S

DAY = "2026-01-12"  # a Monday


def rows():
    out = []
    L.add(out, "Approve the outline", needs="Say yes or no", goal="speaking", blocks=True, day="2026-01-09")
    L.add(out, "Pick a call time", needs="Pick a time", due="2026-01-14", thread="t-204", day="2026-01-10")
    L.add(out, "Renew the plan", needs="Say renew or cancel", day="2026-01-05")
    return out


def rules_hit(found):
    return sorted({f["rule"] for f in found})


class ScriptRulesTest(unittest.TestCase):
    def test_rule_1_answered_is_never_asked_again(self):
        r = rows()
        L.apply_answers(r, [{"id": "approve-the-outline", "answer": "yes"}], "2026-01-11")
        out, found, _ = S.judge({"decisions": [{"id": "approve-the-outline", "question": "Approve?"}]}, r, DAY)
        self.assertEqual(out["decisions"], [])
        self.assertEqual(rules_hit(found), [1])

    def test_rule_1_not_now_sleeps(self):
        r = rows()
        L.sleep(r, "renew-the-plan", "2026-01-19")
        out, found, _ = S.judge({"decisions": [{"id": "renew-the-plan", "question": "Renew?"}]}, r, DAY)
        self.assertEqual((out["decisions"], rules_hit(found)), ([], [1]))

    def test_rule_2_three_mornings_then_rest_until_friday(self):
        state = {"asked": {"renew-the-plan": ["2026-01-07", "2026-01-08", "2026-01-09"]}}
        ask = {"decisions": [{"id": "renew-the-plan", "question": "Renew?"}]}
        out, found, _ = S.judge(ask, rows(), DAY, state)
        self.assertEqual((out["decisions"], rules_hit(found)), ([], [2]))
        out, found, _ = S.judge(ask, rows(), "2026-01-16", state)  # Friday: it returns
        self.assertEqual((len(out["decisions"]), found), (1, []))

    def test_rule_2_a_date_before_friday_beats_the_rest(self):
        state = {"asked": {"pick-a-call-time": ["2026-01-07", "2026-01-08", "2026-01-09"]}}
        out, found, _ = S.judge({"decisions": [{"id": "pick-a-call-time", "question": "Pick?"}]}, rows(), DAY, state)
        self.assertEqual((len(out["decisions"]), found), (1, []))

    def test_rule_3_one_writer_one_row_per_matter(self):
        r = rows()
        ops = [{"op": "add", "title": "Pick a call time"}, {"op": "add", "title": "Other words", "thread": "t-204"},
               {"op": "add", "title": "  "}, {"op": "add", "title": "Book the car service", "needs": "Pick a day"},
               {"op": "delete", "id": "renew-the-plan"}]
        out, found, _ = S.judge({"ledger_ops": ops}, r, DAY)
        self.assertEqual(len(r), 4)
        self.assertEqual(r[-1]["title"], "Book the car service")
        self.assertEqual([f["rule"] for f in found], [3, 3, 3, 3])
        self.assertEqual(L.find(r, "renew-the-plan")["status"], "open")

    def test_rule_3_a_new_decision_becomes_a_row(self):
        r = rows()
        out, _, _ = S.judge({"decisions": [{"id": "new", "title": "Answer the school", "question": "Say yes?", "due": "2026-01-20"}]}, r, DAY)
        self.assertEqual(out["decisions"][0]["id"], "answer-the-school")
        self.assertEqual(L.find(r, "answer-the-school")["needs"], "Say yes?")

    def test_rule_4_only_free_times_are_offered(self):
        busy = [["2026-01-14T09:30", "2026-01-14T10:30"]]
        ask = {"decisions": [{"id": "pick-a-call-time", "question": "Offer?", "offers": ["2026-01-14T10:00", "2026-01-15T12:30"]}]}
        out, found, _ = S.judge(ask, rows(), DAY, busy=busy)
        self.assertEqual(out["decisions"][0]["offers"], ["2026-01-15T12:30"])
        self.assertEqual(rules_hit(found), [4])
        ask["decisions"][0]["offers"] = ["2026-01-14T10:15"]
        out, found, _ = S.judge(ask, rows(), DAY, busy=busy)
        self.assertEqual(out["decisions"], [])

    def test_rule_4_a_time_that_ends_as_the_busy_one_starts_is_free(self):
        self.assertFalse(S.clash("2026-01-14T09:00", [["2026-01-14T09:30", "2026-01-14T10:30"]]))
        self.assertTrue(S.clash("2026-01-14T09:15", [["2026-01-14T09:30", "2026-01-14T10:30"]]))

    def test_rule_5_a_thinner_read_never_replaces_a_fuller_one(self):
        r = rows()
        _, _, state = S.judge({"read": {"mail": 30, "calendar": 6}}, r, DAY)
        out, found, _ = S.judge({"read": {"mail": 4}, "ledger_ops": [{"op": "add", "title": "From the thin run"}]}, r, DAY, state)
        self.assertIsNone(out)
        self.assertEqual(rules_hit(found), [5])
        self.assertEqual(len(r), 3)

    def test_rule_6_weekdays_are_computed(self):
        text, wrong = S.fix_weekdays("Reply by Fri Jan 22, then Monday, Jan 19, 2026 and Tuesday Jan 20.", DAY)
        self.assertEqual(text, "Reply by Thu Jan 22, then Monday, Jan 19, 2026 and Tuesday Jan 20.")
        self.assertEqual(wrong, 1)
        self.assertEqual(S.fix_weekdays("Due Wednesday, January 16, 2026", DAY)[0], "Due Friday, January 16, 2026")
        self.assertEqual(S.fix_weekdays("in December: Mon Jan 5", "2026-12-20")[0], "in December: Tue Jan 5")
        self.assertEqual(S.fix_weekdays("Fri Feb 30", DAY), ("Fri Feb 30", 0))

    def test_rule_6_runs_on_every_text_of_the_proposal(self):
        out, found, _ = S.judge({"headline": "Trip on Fri Jan 22", "plan": ["Form due Sat Jan 16"]}, rows(), DAY)
        self.assertEqual((out["headline"], out["plan"]), ("Trip on Thu Jan 22", ["Form due Fri Jan 16"]))
        self.assertEqual(rules_hit(found), [6])

    def test_rule_7_yesterdays_heads_up_is_not_news(self):
        state = {"heads_up": {"2026-01-11": ["The school closes early on Jan 19."]}}
        out, found, state = S.judge({"heads_up": ["the school closes early on Jan 19", "Two drafts wait."]}, rows(), DAY, state)
        self.assertEqual(out["heads_up"], ["Two drafts wait."])
        self.assertEqual(rules_hit(found), [7])
        out, found, _ = S.judge({"heads_up": ["Two drafts wait."]}, rows(), DAY, state)  # the same day again: still news today
        self.assertEqual((out["heads_up"], found), (["Two drafts wait."], []))

    def test_rule_8_an_id_the_list_does_not_hold_is_dropped(self):
        r = rows()
        L.close(r, "renew-the-plan", "cancelled", day="2026-01-11")
        out, found, _ = S.judge({"decisions": [{"id": "ghost", "question": "?"}, {"id": "renew-the-plan", "question": "?"}],
                                 "ledger_ops": [{"op": "done", "id": "ghost-2"}]}, r, DAY)
        self.assertEqual(out["decisions"], [])
        self.assertEqual([f["rule"] for f in found], [8, 8, 8])

    def test_rule_9_the_page_test(self):
        r = rows()
        page = build_page.build(r, {"decisions": []}, DAY)
        self.assertEqual(S.page_test(page, r, DAY), [])
        self.assertEqual(S.page_test(page.replace('data-id="renew-the-plan"', ""), r, DAY), ["renew-the-plan"])

    def test_the_proposal_and_the_state_given_are_not_changed(self):
        ask, state = {"decisions": [{"id": "new", "title": "A", "question": "A?"}], "headline": "Fri Jan 22"}, {"asked": {}}
        S.judge(ask, rows(), DAY, state)
        self.assertEqual((ask["decisions"][0]["id"], ask["headline"], state), ("new", "Fri Jan 22", {"asked": {}}))


if __name__ == "__main__":
    unittest.main()
