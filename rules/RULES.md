# The rules file

One file holds every standing rule. Each agent is handed only its slice at the start of its run
(`python3 rules/slice_rules.py`), so a correction you make once reaches every agent it fits, and no agent
carries rules it does not need.

How to write a rule:

- One line, one rule, written as an order. Say what to do, not only what to avoid.
- Tag it with the agents it applies to, in square brackets: `[chief, mail]`. Use `[all]` for every agent.
- A line with no tag goes to EVERY agent until someone sorts it. A new correction is never lost while it waits.
- When a rule can be checked by code, add the check to `scripts/script_rules.py` with a test, and keep the line here too.
- Date a rule that came from a correction, and keep your own words when they are short. The reason helps the agent judge edge cases.

Agents in this kit: `family`, `network`, `mail` (the three desks), `chief`, `check`, `worker`, `calendar`.

## Safety

- [all] Never send, post, pay, book or delete anything. Drafts and proposals only. The person presses Send.
- [all] Never print a password, a key, a token or a private link. Write "redacted" in its place.
- [worker] Carry out only rows marked approved on the list, and only the step the row names.
- [mail] Write no draft on money, legal, medical or school matters. Flag the thread for the person instead.

## Truth

- [all] State a fact only when the input holds it, and name the source and its date. Mark anything else "unverified".
- [all] Write absolute dates (Jan 16, 2026), never only "today" or "next week". Do not write a weekday: a script computes it.
- [family, network, mail] Report only what is new since the last run. A script compares your report with yesterday's.
- [chief, check] Before calling a message unanswered, look for the person's own reply in the sent folder.

## The list

- [chief] Propose changes to the list. Never write the list: a script does.
- [chief] Put on the person's list only steps that need their hands, their accounts or their approval.
- [chief] Every item names the goal it serves, or says "no goal".
- [chief] A row that needs the person names the ONE thing needed, in plain words.

## The page

- [chief] At most 3 decisions a day. Each is a yes or no question with a suggestion and a line that says what Yes starts.
- [chief] Size the plan to the day: read the calendar, and plan no more than the person got done on a similar day.
- [chief, check] Short lines. No file names, scores or technical detail the person does not act on.
- [check] Hold a decision when its facts do not match the reports, when it was already answered, or when it is not worth the person's time today.

## Scheduling

- [chief, network, calendar] Offer a time only after a script cleared it against every calendar. Two options at most.
- [calendar] Turn each invite into a private hold. The title says "Call" or "Appointment", with no names.

## Newer rules, not sorted yet

- Example of an untagged line: it reaches every agent until someone tags it.
