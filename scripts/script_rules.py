#!/usr/bin/env python3
"""The script rules: plain code that runs on every run, before anything reaches you. No AI here.

Each rule started as a mistake an agent made more than once. A mistake a script can catch is caught by a script: it costs
nothing, it runs every time and it has a test. The AI look that follows is kept for what needs judgment (does this decision
make sense, is this draft right).

  1. An item you answered never becomes a decision again.
  2. An ask with no answer after 3 mornings rests until Friday, unless its date falls before then.
  3. One writer of the list: the chief proposes, this script writes. One row per matter.
  4. A time is never offered unless your calendar is free then.
  5. A run that read less never replaces a run that read more.
  6. A weekday next to a date is computed, never taken from the AI.
  7. A heads-up said yesterday is not news today.
  8. Open and closed are read from the list: an id the list does not hold is dropped.
  9. The page test: every item that needs you is on the page.

  python3 scripts/script_rules.py out/2026-01-12/chief.json --day 2026-01-12 --state out/state.json [--busy busy.json] [--dry]

Rules 1 to 8 run on the chief's proposal (judge). Rule 9 runs on the finished page (page_test).
Add your own: one function, one line in the list above, one test. Tests: python3 -m unittest discover tests
"""
import argparse, datetime, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)([a-z]*)(,?\s+)(" + "|".join(MONTHS) + r")([a-z]*\.?\s+)(\d{1,2})(?:(,\s+)(\d{4}))?")
MAY_PROPOSE = ("add", "done")


def fix_weekdays(text, day):
    """Rule 6. Returns (the text with every weekday recomputed from its date, how many were wrong)."""
    base, wrong = datetime.date.fromisoformat(day), 0

    def sub(m):
        nonlocal wrong
        try:
            d = datetime.date(int(m.group(8)) if m.group(8) else base.year, MONTHS.index(m.group(4)) + 1, int(m.group(6)))
            if not m.group(8) and d < base - datetime.timedelta(days=60):
                d = d.replace(year=d.year + 1)  # "Jan 5" written in December means next January
        except ValueError:
            return m.group(0)
        if WD[d.weekday()] == m.group(1):
            return m.group(0)
        wrong += 1
        name = d.strftime("%A") if m.group(2) else WD[d.weekday()]
        return name + m.group(0)[len(m.group(1)) + len(m.group(2)):]

    return DATE.sub(sub, text), wrong


def walk(x, fn):
    if isinstance(x, str):
        return fn(x)
    if isinstance(x, list):
        return [walk(v, fn) for v in x]
    if isinstance(x, dict):
        return {k: walk(v, fn) for k, v in x.items()}
    return x


def clash(start, busy, minutes=30):
    """Rule 4. True when the offered time touches a busy stretch. Times are ISO text, for example 2026-01-20T10:00."""
    a = datetime.datetime.fromisoformat(start)
    b = a + datetime.timedelta(minutes=minutes)
    return any(datetime.datetime.fromisoformat(s) < b and a < datetime.datetime.fromisoformat(e) for s, e in busy)


def judge(proposal, rows, day, state=None, busy=()):
    """Rules 1 to 8 on the chief's proposal. Changes `rows` (this is the one writer). Returns (proposal or None, findings, state).

    None means the whole proposal is set aside (rule 5) and the earlier one stays."""
    state = json.loads(json.dumps(state or {}))
    out = json.loads(json.dumps(proposal))
    found = []

    def say(rule, text):
        found.append({"rule": rule, "text": text})

    # 5. a thinner read never replaces a fuller one
    total, before = sum((out.get("read") or {}).values()), (state.get("read") or {}).get(day, 0)
    if total < before:
        say(5, f"this run read {total} items and an earlier run today read {before}: the earlier run stays")
        return None, found, state
    state.setdefault("read", {})[day] = total

    # 6. weekdays are computed
    wrong = [0]

    def fx(text):
        fixed, n = fix_weekdays(text, day)
        wrong[0] += n
        return fixed

    out = walk(out, fx)
    if wrong[0]:
        say(6, f"{wrong[0]} weekday(s) did not match the date and were recomputed")

    # 3 and 8. the chief proposes changes to the list, this script writes them
    for op in out.get("ledger_ops", []):
        kind = op.get("op")
        if kind not in MAY_PROPOSE:
            say(3, f"'{kind}' is not a change the chief may propose: dropped")
        elif kind == "add":
            if not (op.get("title") or "").strip():
                say(3, "an add with no title was dropped")
                continue
            row, new = L.add(rows, op["title"], op.get("owner", "you"), op.get("needs", ""), op.get("goal", ""),
                             op.get("blocks", False), op.get("due", ""), op.get("thread", ""), day)
            if not new:
                say(3, f"'{op['title']}' is already on the list as {row['id']}: no second row")
        else:
            try:
                L.close(rows, op.get("id"), op.get("note", ""), day=day)
            except KeyError:
                say(8, f"close '{op.get('id')}': the list holds no such row, dropped")

    # 1, 2, 4, 8. the decisions
    date = datetime.date.fromisoformat(day)
    friday = (date + datetime.timedelta(days=(4 - date.weekday()) % 7)).isoformat()
    asked, keep = state.setdefault("asked", {}), []
    for d in out.get("decisions", []):
        if d.get("id") in (None, "", "new"):
            row, new = L.add(rows, d.get("title") or d.get("question", ""), "you", d.get("question", ""), d.get("goal", ""),
                             d.get("blocks", False), d.get("due", ""), d.get("thread", ""), day)
            d["id"] = row["id"]
        try:
            row = L.find(rows, d["id"])
        except KeyError:
            say(8, f"decision on '{d['id']}': the list holds no such row, dropped")
            continue
        if row["status"] != "open":
            say(8, f"{row['id']} is closed on the list: not asked")
        elif row.get("answered"):
            say(1, f"{row['id']} was answered on {row['answered']}: not asked again")
        elif L.asleep(row, day):
            say(1, f"{row['id']} sleeps until {row['wake']} on your 'not now': not asked")
        elif len([x for x in asked.get(row["id"], []) if x < day]) >= 3 and day != friday and not (row.get("due") and row["due"] <= friday):
            say(2, f"{row['id']} was asked on 3 mornings with no answer: it rests until Friday {friday}")
        else:
            if d.get("offers"):
                free = [t for t in d["offers"] if not clash(t, busy)]
                if len(free) < len(d["offers"]):
                    say(4, f"{row['id']}: {len(d['offers']) - len(free)} offered time(s) are not free on your calendar")
                if not free:
                    say(4, f"{row['id']}: no offered time is free, held until new times are found")
                    continue
                d["offers"] = free
            keep.append(d)
            if day not in asked.setdefault(row["id"], []):
                asked[row["id"]].append(day)
    out["decisions"] = keep

    # 7. yesterday's heads-up is not news
    said = state.setdefault("heads_up", {})
    old = {L.norm(x) for k, v in said.items() if k < day for x in v}
    fresh = [x for x in out.get("heads_up", []) if L.norm(x) not in old]
    if len(fresh) < len(out.get("heads_up", [])):
        say(7, f"{len(out.get('heads_up', [])) - len(fresh)} heads-up line(s) were said on an earlier day: dropped")
    out["heads_up"] = fresh
    said[day] = sorted(set(said.get(day, []) + fresh))
    return out, found, state


def page_test(html, rows, day):
    """Rule 9. The ids of rows that need you and are not on the page. An empty list means the page holds everything."""
    return [r["id"] for r in L.open_rows(rows, day, owner="you") if f'data-id="{r["id"]}"' not in html]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rules 1 to 8 on the chief's proposal.")
    ap.add_argument("proposal"); ap.add_argument("--day", default=L.today()); ap.add_argument("--state", default="")
    ap.add_argument("--busy", default=""); ap.add_argument("--dry", action="store_true", help="show what would change, write nothing")
    args = ap.parse_args(argv)
    rows = L.load()
    state = json.loads(Path(args.state).read_text()) if args.state and Path(args.state).exists() else {}
    busy = json.loads(Path(args.busy).read_text()) if args.busy else []
    out, found, state = judge(json.loads(Path(args.proposal).read_text()), rows, args.day, state, busy)
    for f in found:
        print(f"rule {f['rule']}: {f['text']}")
    print(f"{len(found)} finding(s); " + ("the proposal is set aside" if out is None else f"{len(out['decisions'])} decision(s) pass"))
    if not args.dry:
        L.save(rows, event={"day": args.day, "cmd": "script_rules", "findings": len(found)})
        if args.state:
            Path(args.state).write_text(json.dumps(state, indent=1))
        if out is not None:
            Path(args.proposal).with_name("checked.json").write_text(json.dumps({"proposal": out, "findings": found}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
