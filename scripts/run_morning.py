#!/usr/bin/env python3
"""The morning run: scripts set the order. Each agent is started here, in its turn, and no agent calls another.

  1. scripts read first, no AI      your readers write out/DAY/reads.json (mail, calendars, any page you follow)
  2. the rules file is sliced       each agent gets only its rules
  3. the desks report               one agent call per desk
  4. the chief proposes             one agent call
  5. the script rules               plain code: rules 1 to 8, and the one writer of the list
  6. the page is built              three tiers, three decisions at most
  7. the page test and self-check   rule 9, then the run looks for its own faults

  python3 scripts/run_morning.py --demo                 the whole run on the sample files in examples/, with no AI and no accounts
  AGENT_CMD="your-agent-cli --print" python3 scripts/run_morning.py

AGENT_CMD is any command that reads a prompt on standard input and prints the agent's answer (JSON) on standard output.
Without --demo, step 1 is yours: put your readers before this script and have them write out/DAY/reads.json.
"""
import argparse, datetime, json, os, shlex, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "rules"))
import build_page, ledger as L, script_rules, selfcheck, slice_rules  # noqa: E402

DESKS = ("family", "network", "mail")
DEMO_DAY = "2026-01-12"


def ask_agent(name, prompt_file, rules_text, payload, timeout=900):
    """Start one agent: its rules, its prompt, its input. Returns the JSON it printed."""
    cmd = os.environ.get("AGENT_CMD")
    if not cmd:
        raise SystemExit("AGENT_CMD is not set. Use --demo to run on the sample files, or set AGENT_CMD to your agent command.")
    prompt = f"{rules_text}\n\n{Path(prompt_file).read_text()}\n\n## Your input\n\n```json\n{json.dumps(payload, indent=1)}\n```\n"
    r = subprocess.run(shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=timeout)
    text = r.stdout
    if r.returncode != 0 or "{" not in text:
        raise RuntimeError(f"the {name} agent returned no JSON (exit {r.returncode})")
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def run(day, out_root, demo=False, ledger_path=None, log=print):
    folder = Path(out_root) / day
    (folder / "reports").mkdir(parents=True, exist_ok=True)
    ex = ROOT / "examples"
    if demo:  # the demo starts from the sample list, so it gives the same page every time
        shutil.copy(ex / "ledger.json", ledger_path)
        shutil.copy(ex / "state.json", Path(out_root) / "state.json")
        shutil.copy(ex / "reads.json", folder / "reads.json")
    rows = L.load(ledger_path)
    state_file = Path(out_root) / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    reads = json.loads((folder / "reads.json").read_text())
    log(f"1. scripts read first, no AI: {sum(len(v) for v in reads.values())} items from {len(reads)} sources")

    rules = (ROOT / "rules/RULES.md").read_text()
    log(f"2. rules sliced: {len(slice_rules.parse(rules))} rules, each agent gets only its own")

    reports = {}
    for desk in DESKS:
        if demo:
            reports[desk] = json.loads((ex / f"reports/{desk}.json").read_text())
        else:
            prompt = ROOT / f"agents/{desk}.md"
            reports[desk] = ask_agent(desk, prompt if prompt.exists() else ROOT / "agents/desk.md", slice_rules.slice_for(rules, desk),
                                      {"reads": reads, "open_rows": L.open_rows(rows, day)})
        (folder / f"reports/{desk}.json").write_text(json.dumps(reports[desk], indent=1))
    log("3. three desks report: " + ", ".join(f"{d} {len(reports[d].get('needs_you', []))} for you" for d in DESKS))

    if demo:
        proposal = json.loads((ex / "chief.json").read_text())
    else:
        proposal = ask_agent("chief", ROOT / "agents/chief.md", slice_rules.slice_for(rules, "chief"),
                             {"goals": (ROOT / "examples/goals.md").read_text(), "reports": reports, "open_rows": L.open_rows(rows, day)})
    (folder / "chief.json").write_text(json.dumps(proposal, indent=1))
    log(f"4. the chief proposes: {len(proposal.get('decisions', []))} decisions, {len(proposal.get('ledger_ops', []))} changes to the list")

    busy = json.loads((ex / "busy.json").read_text()) if demo else reads.get("busy", [])
    checked, found, state = script_rules.judge(proposal, rows, day, state, busy)
    for f in found:
        log(f"   rule {f['rule']}: {f['text']}")
    if checked is None:
        log("5. the script rules set this proposal aside: the earlier page stays")
        return {"folder": folder, "findings": found, "page": None}
    L.save(rows, ledger_path, event={"day": day, "cmd": "run_morning"})
    state_file.write_text(json.dumps(state, indent=1))
    (folder / "checked.json").write_text(json.dumps({"proposal": checked, "findings": found}, indent=1))
    log(f"5. the script rules: {len(found)} finding(s), {len(checked['decisions'])} decision(s) pass")

    page = build_page.build(rows, checked, day)
    (folder / "page.html").write_text(page)
    log(f"6. the page: {Path(out_root).name}/{day}/page.html")

    missing = script_rules.page_test(page, rows, day)
    s = selfcheck.run_checks(selfcheck.Run(folder, day, rows, DESKS), save=lambda r: L.save(r, ledger_path, event={"day": day, "cmd": "selfcheck"}))
    log(f"7. page test: {'every item that needs you is on the page' if not missing else 'MISSING ' + ', '.join(missing)}; "
        f"self-check: {s['faults']} fault(s), {s['fixed']} fixed by script, {s['filed']} filed as a row")
    for x in s["lines"]:
        log("   FOR YOU: " + x)
    return {"folder": folder, "findings": found, "page": folder / "page.html", "missing": missing, "selfcheck": s}


def main(argv=None):
    ap = argparse.ArgumentParser(description="The morning run.")
    ap.add_argument("--demo", action="store_true", help="run on the sample files, with no AI and no accounts")
    ap.add_argument("--day", default=""); ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    day = args.day or (DEMO_DAY if args.demo else datetime.date.today().isoformat())
    out = Path(args.out or ROOT / ("out-demo" if args.demo else "out"))
    out.mkdir(parents=True, exist_ok=True)
    run(day, out, args.demo, out / "ledger.json" if args.demo else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
