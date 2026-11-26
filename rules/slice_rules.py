#!/usr/bin/env python3
"""One rules file, each agent handed only its slice. No AI here.

rules/RULES.md holds every rule. A rule line starts with the agents it applies to in square brackets:
  - [chief, mail] Offer a time only after a script cleared it.
  - [all] Never send anything.
  - A line with no tag goes to every agent until someone sorts it.

  python3 rules/slice_rules.py            writes rules/slices/<agent>.md for every agent and prints one line
  python3 rules/slice_rules.py chief      prints the chief's slice

Run it at the start of every run, so each agent reads today's rules. Tests: python3 -m unittest discover tests
"""
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = ("family", "network", "mail", "chief", "check", "worker", "calendar")
RULE = re.compile(r"^- (?:\[([^\]]*)\]\s*)?(.+)$")


def parse(text):
    """Every rule under the first '## ' heading as (section, tags, rule). Tags None means the line has no tag yet."""
    out, section = [], None
    for raw in text.splitlines():
        if raw.startswith("## "):
            section = raw[3:].strip()
            continue
        m = RULE.match(raw.strip())
        if section is None or not m:
            continue
        tags = None if m.group(1) is None else {t.strip().lower() for t in m.group(1).split(",") if t.strip()}
        out.append((section, tags, m.group(2).strip()))
    return out


def unknown_tags(text, agents=AGENTS):
    """Tags that name no agent: a misspelled tag would silently hide a rule from the agent it was meant for."""
    return sorted({t for _, tags, _ in parse(text) for t in (tags or ()) if t != "all" and t not in agents})


def slice_for(text, agent):
    """The rules for one agent: its own, the ones for all, and every line nobody tagged yet."""
    lines, last = [f"# Standing rules for the {agent} agent", "",
                   "These are orders, not suggestions. When two seem to clash, the more careful one wins.", ""], None
    for section, tags, rule in parse(text):
        if tags is not None and "all" not in tags and agent not in tags:
            continue
        if section != last:
            lines += ["", f"## {section}", ""] if last else [f"## {section}", ""]
            last = section
        lines.append(f"- {rule}" + ("" if tags is not None else " (not sorted yet: applies to every agent)"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = (HERE / "RULES.md").read_text()
    bad = unknown_tags(text)
    if bad:
        print("unknown tag(s) in RULES.md: " + ", ".join(bad) + ". Fix the tag or add the agent to AGENTS.")
        return 1
    if argv:
        if argv[0] not in AGENTS:
            print(f"no agent '{argv[0]}'. Agents: {', '.join(AGENTS)}")
            return 1
        print(slice_for(text, argv[0]), end="")
        return 0
    out = HERE / "slices"
    out.mkdir(exist_ok=True)
    counts = []
    for a in AGENTS:
        s = slice_for(text, a)
        (out / f"{a}.md").write_text(s)
        counts.append(f"{a} {sum(1 for x in s.splitlines() if x.startswith('- '))}")
    print("slices written: " + ", ".join(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
