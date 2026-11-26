#!/usr/bin/env python3
"""The one list. Every open item lives here and nowhere else.

One writer: only this script changes the file. Agents propose, scripts write.

  python3 scripts/ledger.py add "Send the invoice" --owner you --due 2026-01-16 --goal money --needs "Press Send on the draft"
  python3 scripts/ledger.py brief                  the open list, grouped by who holds the next step
  python3 scripts/ledger.py done ID "what closed it"
  python3 scripts/ledger.py drop ID "why"
  python3 scripts/ledger.py sleep ID 2026-01-23    your "not now": the row returns on that day
  python3 scripts/ledger.py check ID "what I read"  the row was re-read against the live source
  python3 scripts/ledger.py verify                 rows nobody re-checked, rows past due, rows that name no step
  python3 scripts/ledger.py answers FILE           writes your Yes and Not now taps to the list, with no AI

The file is data/ledger.json (set LEDGER to move it). Every change is also appended to a log beside it, one line per change.
Tests: python3 -m unittest discover tests
"""
import argparse, datetime, json, os, re, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIERS = ("blocks", "dated", "wait")
TIER_NAMES = {"blocks": "Blocks a goal", "dated": "Has a date", "wait": "Can wait"}
OWNERS = ("you", "agent", "other")


def ledger_file():
    return Path(os.environ.get("LEDGER") or ROOT / "data/ledger.json")


def today():
    return datetime.date.today().isoformat()


def load(path=None):
    p = Path(path or ledger_file())
    return json.loads(p.read_text()) if p.exists() else []


def save(rows, path=None, event=None):
    """Write the whole list in one move, so a crash never leaves half a file."""
    p = Path(path or ledger_file())
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    if event:
        with open(p.with_name(p.stem + "-log.jsonl"), "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def slug(title, rows):
    base = "-".join(norm(title).split()[:5]) or "row"
    ids, out, k = {r["id"] for r in rows}, base, 2
    while out in ids:
        out, k = f"{base}-{k}", k + 1
    return out


def find(rows, rid):
    for r in rows:
        if r["id"] == rid:
            return r
    raise KeyError(f"the list holds no row '{rid}'")


def same_matter(rows, title, thread=""):
    """The open row that already holds this matter, or None: the same mail thread, or the same words in the title."""
    for r in rows:
        if r["status"] != "open":
            continue
        if thread and r.get("thread") == thread:
            return r
        if norm(r["title"]) == norm(title):
            return r
    return None


def add(rows, title, owner="you", needs="", goal="", blocks=False, due="", thread="", day=None):
    """Add a row and return (row, True). When the matter is already on the list, return (that row, False): one row per matter."""
    if owner not in OWNERS:
        raise ValueError(f"owner must be one of {OWNERS}")
    if due:
        datetime.date.fromisoformat(due)
    old = same_matter(rows, title, thread)
    if old:
        return old, False
    row = {"id": slug(title, rows), "title": title.strip(), "owner": owner, "needs": needs, "goal": goal,
           "blocks": bool(blocks and goal), "due": due, "thread": thread, "status": "open", "created": day or today(),
           "checked": "", "wake": "", "approved": False, "answered": "", "note": ""}
    rows.append(row)
    return row, True


def close(rows, rid, note="", status="done", day=None):
    row = find(rows, rid)
    row.update(status=status, closed=day or today(), note=note)
    return row


def sleep(rows, rid, wake):
    datetime.date.fromisoformat(wake)
    row = find(rows, rid)
    row["wake"] = wake
    return row


def check(rows, rid, note, day=None):
    row = find(rows, rid)
    row.update(checked=day or today(), note=note)
    return row


def asleep(row, day):
    return bool(row.get("wake")) and row["wake"] > day


def tier(row):
    """Where the row sits on your page: it blocks a goal, it has a date, or it can wait."""
    if row.get("blocks") and row.get("goal"):
        return "blocks"
    return "dated" if row.get("due") else "wait"


def open_rows(rows, day, owner=None):
    out = [r for r in rows if r["status"] == "open" and not asleep(r, day) and (owner is None or r["owner"] == owner)]
    return sorted(out, key=lambda r: (TIERS.index(tier(r)), r.get("due") or "9999", r["created"], r["id"]))


def verify(rows, day, stale_days=3):
    """What is wrong with the list itself. A list nobody re-reads turns into a list nobody trusts."""
    limit = (datetime.date.fromisoformat(day) - datetime.timedelta(days=stale_days)).isoformat()
    out = []
    for r in open_rows(rows, day):
        if r["owner"] == "you" and not r.get("needs"):
            out.append({"id": r["id"], "problem": "needs you, but names no step for you"})
        if r.get("due") and r["due"] < day:
            out.append({"id": r["id"], "problem": f"past due since {r['due']}"})
        if not r.get("checked"):
            if r["created"] < limit:
                out.append({"id": r["id"], "problem": "never re-checked against the live source"})
        elif r["checked"] < limit:
            out.append({"id": r["id"], "problem": f"not re-checked since {r['checked']}"})
    return out


def apply_answers(rows, answers, day, rest_days=7):
    """Your taps, written by a script. Yes hands the row to the worker; Not now puts it to sleep. Returns the ids it did not know."""
    unknown = []
    for a in answers:
        try:
            row = find(rows, a.get("id"))
        except KeyError:
            unknown.append(a.get("id"))
            continue
        if a.get("answer") == "yes":
            row.update(approved=True, owner="agent", needs="", answered=day)
        elif a.get("answer") == "not_now":  # it may be asked again once it wakes
            row["wake"] = a.get("until") or (datetime.date.fromisoformat(day) + datetime.timedelta(days=rest_days)).isoformat()
        else:
            unknown.append(a.get("id"))
    return unknown


def brief(rows, day):
    lines, groups = [], (("you", "NEEDS YOU"), ("agent", "THE AGENTS ARE ON"), ("other", "WAITING ON OTHERS"))
    for owner, name in groups:
        mine = open_rows(rows, day, owner)
        lines.append(f"{name} ({len(mine)})")
        for i, r in enumerate(mine, 1):
            bits = [f" {i}. [{r['id']}] {r['title']}", TIER_NAMES[tier(r)]]
            if r.get("due"):
                bits.append(("PAST DUE, was due " if r["due"] < day else "due ") + r["due"])
            if r.get("needs"):
                bits.append("needs: " + r["needs"])
            bits.append("checked " + r["checked"] if r.get("checked") else "never re-checked")
            lines.append(" | ".join(bits))
    resting = sum(1 for r in rows if r["status"] == "open" and asleep(r, day))
    if resting:
        lines.append(f"{resting} more asleep on your 'not now'; each returns on its day")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The one list.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("title"); a.add_argument("--owner", default="you", choices=OWNERS)
    a.add_argument("--needs", default=""); a.add_argument("--goal", default=""); a.add_argument("--blocks", action="store_true")
    a.add_argument("--due", default=""); a.add_argument("--thread", default="")
    for name in ("done", "drop", "check"):
        s = sub.add_parser(name); s.add_argument("id"); s.add_argument("note", nargs="?", default="")
    s = sub.add_parser("sleep"); s.add_argument("id"); s.add_argument("wake")
    sub.add_parser("brief"); sub.add_parser("verify")
    s = sub.add_parser("answers"); s.add_argument("file")
    args = ap.parse_args(argv)
    rows, day = load(), today()
    try:
        if args.cmd == "add":
            row, new = add(rows, args.title, args.owner, args.needs, args.goal, args.blocks, args.due, args.thread)
            print(("added " if new else "already on the list as ") + row["id"])
            if not new:
                return 0
        elif args.cmd in ("done", "drop"):
            close(rows, args.id, args.note, "done" if args.cmd == "done" else "dropped")
            print(f"{args.id}: closed")
        elif args.cmd == "check":
            check(rows, args.id, args.note)
            print(f"{args.id}: re-checked {day}")
        elif args.cmd == "sleep":
            sleep(rows, args.id, args.wake)
            print(f"{args.id}: asleep until {args.wake}")
        elif args.cmd == "answers":
            unknown = apply_answers(rows, json.loads(Path(args.file).read_text()), day)
            print("answers written" + (f"; not on the list: {', '.join(map(str, unknown))}" if unknown else ""))
        elif args.cmd == "brief":
            print(brief(rows, day))
            return 0
        elif args.cmd == "verify":
            bad = verify(rows, day)
            print("\n".join(f"{b['id']}: {b['problem']}" for b in bad) or "the list is clean")
            return 1 if bad else 0
    except (KeyError, ValueError) as e:
        print(e.args[0] if e.args else str(e))
        return 2
    save(rows, event={"day": day, "cmd": args.cmd, "args": {k: v for k, v in vars(args).items() if k != "cmd"}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
