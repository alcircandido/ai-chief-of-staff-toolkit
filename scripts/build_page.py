#!/usr/bin/env python3
"""The page: one page a day, three decisions at most, everything else in three tiers.

  1. Blocks a goal   decide this first
  2. Has a date      soonest first
  3. Can wait        ideas and extras: counted every day, listed in full on Friday

Each decision is a yes or no question with a suggestion and a line that says what Yes starts. Your taps are collected into one
block of text; save it as a file and `python3 scripts/ledger.py answers FILE` writes them to the list. No AI in this script.

  python3 scripts/build_page.py out/2026-01-12/checked.json --day 2026-01-12 > out/2026-01-12/page.html
"""
import argparse, datetime, html, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

MAX_DECISIONS = 3
E = html.escape
CSS = """body{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#1a1f2e}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}.sub{color:#5a6478;margin:0 0 18px}
.card{border:1px solid #d9dee8;border-radius:12px;padding:14px 16px;margin:10px 0}.card b{font-size:17px}
.card p{margin:6px 0}.note{color:#5a6478;font-size:14px}
button{font:inherit;padding:8px 18px;border-radius:10px;border:1px solid #1a1f2e;background:#fff;margin:6px 8px 0 0;cursor:pointer}
button.on{background:#1a1f2e;color:#fff}li{margin:6px 0}summary{cursor:pointer;font-weight:600}
textarea{width:100%;height:90px;font:13px/1.4 ui-monospace,monospace;margin-top:8px}"""
JS = """const picks={};document.querySelectorAll('button[data-answer]').forEach(b=>b.onclick=()=>{
const id=b.closest('[data-id]').dataset.id;picks[id]=b.dataset.answer;
b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
document.getElementById('answers').value=JSON.stringify(Object.entries(picks).map(([id,answer])=>({id,answer})),null,1)})"""


def line(row, day):
    bits = [E(row["title"])]
    if row.get("due"):
        bits.append(("past due, was due " if row["due"] < day else "due ") + row["due"])
    if row.get("goal"):
        bits.append("goal: " + E(row["goal"]))
    if row.get("needs"):
        bits.append(E(row["needs"]))
    return f'<li data-id="{E(row["id"])}">' + " · ".join(bits) + "</li>"


def build(rows, proposal, day, friday=None):
    """The page as HTML. Every row that needs you carries data-id, so rule 9 (the page test) can count them."""
    date = datetime.date.fromisoformat(day)
    friday = date.weekday() == 4 if friday is None else friday
    mine = L.open_rows(rows, day, owner="you")
    by_id = {r["id"]: r for r in mine}
    rank = {r["id"]: i for i, r in enumerate(mine)}  # tier first, then the soonest date
    asks = sorted([d for d in proposal.get("decisions", []) if d.get("id") in by_id], key=lambda d: rank[d["id"]])
    top, asked = asks[:MAX_DECISIONS], set()
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
           f"<title>Your page, {day}</title><style>{CSS}</style></head><body>",
           f"<h1>{E(proposal.get('headline') or 'Your page')}</h1>",
           f"<p class='sub'>{date.strftime('%a %b')} {date.day}, {date.year}. {len(top)} decision(s), {len(mine)} open item(s) that need you.</p>"]
    if top:
        out.append("<h2>Decide</h2>")
    for d in top:
        asked.add(d["id"])
        row = by_id[d["id"]]
        out.append(f'<div class="card" data-id="{E(d["id"])}"><b>{E(d.get("question") or row["title"])}</b>'
                   + (f'<p>Suggested: {E(d["suggestion"])}</p>' if d.get("suggestion") else "")
                   + (f'<p class="note">Yes starts: {E(d["yes_starts"])}</p>' if d.get("yes_starts") else "")
                   + f'<p class="note">{L.TIER_NAMES[L.tier(row)]}' + (f' · due {row["due"]}' if row.get("due") else "") + "</p>"
                   + '<button data-answer="yes">Yes</button><button data-answer="not_now">Not now</button></div>')
    for n, t in enumerate(L.TIERS, 1):
        part = [r for r in mine if L.tier(r) == t and r["id"] not in asked]
        if not part:
            continue
        items = "<ul>" + "".join(line(r, day) for r in part) + "</ul>"
        if t == "wait" and not friday:
            out.append(f"<details><summary>{n}. {L.TIER_NAMES[t]}: {len(part)} item(s), listed in full on Friday</summary>{items}</details>")
        else:
            out.append(f"<h2>{n}. {L.TIER_NAMES[t]}</h2>{items}")
    for name, key in (("Heads-up", "heads_up"), ("The plan for today", "plan")):
        if proposal.get(key):
            out.append(f"<h2>{name}</h2><ul>" + "".join(f"<li>{E(x)}</li>" for x in proposal[key]) + "</ul>")
    if friday and proposal.get("ideas"):
        out.append("<h2>New ideas, at most 3</h2><ul>" + "".join(f"<li>{E(x)}</li>" for x in proposal["ideas"][:3]) + "</ul>")
    out.append("<h2>Your answers</h2><p class='note'>Tap Yes or Not now above. Save this block as a file; a script writes it to the list.</p>"
               f"<textarea id='answers' readonly>[]</textarea><script>{JS}</script></body></html>")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the page from the checked proposal and the list.")
    ap.add_argument("checked"); ap.add_argument("--day", default=L.today()); ap.add_argument("--friday", action="store_true")
    args = ap.parse_args(argv)
    data = json.loads(Path(args.checked).read_text())
    print(build(L.load(), data.get("proposal", data), args.day, True if args.friday else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
