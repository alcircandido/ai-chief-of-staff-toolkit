#!/usr/bin/env python3
"""The self-check: a run that finds its own faults, so you are never the one who finds the bug.

It runs last in every run. Each check returns faults. For every fault, in this order:
  1. a script fixes it (the fault carries its own fix), or
  2. it becomes a row on the list, once (the same fault never makes a second row), or
  3. when even the list cannot be written, one plain line is printed for you.
A failure that only sits in a log is not allowed: every fault ends as a fix, a row or a line.

  python3 scripts/selfcheck.py out/2026-01-12 --day 2026-01-12

Add a check: a function that takes the run and returns Fault objects, added to CHECKS. Tests: python3 -m unittest discover tests
"""
import argparse, hashlib, json, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402
import build_page, script_rules  # noqa: E402

STEPS = ("reads.json", "chief.json", "checked.json", "page.html")


@dataclass
class Fault:
    key: str                                 # stable name of the fault, so it is filed once
    line: str                                # one plain line a person can act on
    fix: Optional[Callable[[], bool]] = None  # returns True when the script repaired it


@dataclass
class Run:
    folder: Path
    day: str
    rows: list
    desks: tuple = ()


def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def rebuild_page(run):
    data = read_json(run.folder / "checked.json")
    if not data:
        return False
    (run.folder / "page.html").write_text(build_page.build(run.rows, data.get("proposal", data), run.day))
    return not script_rules.page_test((run.folder / "page.html").read_text(), run.rows, run.day)


def check_steps(run):
    """Every step left its file, and the file can be read."""
    out = []
    for name in STEPS + tuple(f"reports/{d}.json" for d in run.desks):
        p = run.folder / name
        if not p.exists() or p.stat().st_size == 0:
            fix = (lambda: rebuild_page(run)) if name == "page.html" else None
            out.append(Fault(f"missing:{name}", f"The run of {run.day} has no {name}: that step did not finish.", fix))
        elif name.endswith(".json") and read_json(p) is None:
            out.append(Fault(f"unreadable:{name}", f"The run of {run.day} wrote a {name} that cannot be read."))
    return out


def check_reads(run):
    """A desk that read nothing reports nothing: silence must not pass for 'all clear'."""
    out = []
    for d in run.desks:
        rep = read_json(run.folder / f"reports/{d}.json") or {}
        if rep and sum((rep.get("read") or {}).values()) == 0:
            out.append(Fault(f"empty-read:{d}", f"The {d} desk read 0 items on {run.day}: its sources may be down."))
    return out


def check_page(run):
    """Rule 9 again, on the page as it stands on disk."""
    p = run.folder / "page.html"
    if not p.exists():
        return []
    missing = script_rules.page_test(p.read_text(), run.rows, run.day)
    return [Fault("page-test", f"{len(missing)} item(s) that need you are not on the page: {', '.join(missing)}.",
                  lambda: rebuild_page(run))] if missing else []


def check_log(run):
    """A crash inside a step shows in the log even when the step left an old file behind."""
    p = run.folder / "run.log"
    text = p.read_text() if p.exists() else ""
    return [Fault("log-crash", f"The log of {run.day} holds a crash (Traceback). Read {p.name}.")] if "Traceback" in text else []


def check_list(run):
    """The list itself: rows past due, rows that name no step for you."""
    return [Fault(f"list:{b['id']}:{b['problem'][:20]}", f"List row {b['id']}: {b['problem']}.")
            for b in L.verify(run.rows, run.day) if "re-checked" not in b["problem"]]


CHECKS = (check_steps, check_reads, check_page, check_log, check_list)


def fault_id(fault):
    return "fault-" + hashlib.sha1(fault.key.encode()).hexdigest()[:8]


def run_checks(run, checks=CHECKS, save=None):
    """Returns a summary: how many faults, how many a script fixed, how many became a row, and the plain lines left over."""
    faults = [f for c in checks for f in c(run)]
    fixed, filed, lines = 0, 0, []
    for f in faults:
        try:
            if f.fix and f.fix():
                fixed += 1
                continue
        except Exception as e:  # a fix that fails is itself a fault, not a crash of the self-check
            f.line += f" (the automatic fix failed: {type(e).__name__})"
        if f.key.startswith("list:"):
            lines.append(f.line)  # the row is already on the list: say it, do not file a row about a row
            continue
        rid = fault_id(f)
        if any(r["id"] == rid and r["status"] == "open" for r in run.rows):
            continue  # filed on an earlier run and still open: one fault, one row
        run.rows.append({"id": rid, "title": "Self-check: " + f.line, "owner": "agent", "needs": "", "goal": "", "blocks": False,
                         "due": run.day, "thread": "", "status": "open", "created": run.day, "checked": "", "wake": "",
                         "approved": False, "answered": "", "note": f.key})
        filed += 1
    if filed and save:
        try:
            save(run.rows)
        except OSError:
            lines.append(f"{filed} fault(s) could not be written to the list. Open the run folder {run.folder.name} and read run.log.")
            filed = 0
    return {"checks": len(checks), "faults": len(faults), "fixed": fixed, "filed": filed, "lines": lines}


def main(argv=None):
    ap = argparse.ArgumentParser(description="The run checks itself.")
    ap.add_argument("folder"); ap.add_argument("--day", default=L.today()); ap.add_argument("--desks", default="")
    args = ap.parse_args(argv)
    run = Run(Path(args.folder), args.day, L.load(), tuple(x for x in args.desks.split(",") if x))
    s = run_checks(run, save=lambda rows: L.save(rows, event={"day": args.day, "cmd": "selfcheck"}))
    print(f"self-check: {s['checks']} checks, {s['faults']} fault(s): {s['fixed']} fixed by script, {s['filed']} filed as a row")
    for x in s["lines"]:
        print("FOR YOU: " + x)
    return 0 if not s["lines"] else 1


if __name__ == "__main__":
    sys.exit(main())
