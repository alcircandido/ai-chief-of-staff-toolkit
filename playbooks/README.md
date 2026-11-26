# Shared playbooks

A playbook is one file that says how a kind of work is done here: how a text is written, how a picture or a deck
should look, how a call is prepared, how a page is laid out for review. Every agent that does that kind of work reads
the same file. That is what keeps seven agents from producing seven styles.

- **One voice** for texts: `voice.md`
- **One look** for pictures, decks and pages: `look.md`
- **One way to prep** a call: `call-prep.md`
- **One way to check** a run: that one is code, `scripts/selfcheck.py`

## Rules file or playbook?

- A **rule** is one line that is always true: "never send", "two time options at most". It lives in `rules/RULES.md`.
- A **playbook** is the method for a job that repeats: several steps, examples, a check at the end. It lives here.

An agent reads its rules on every run. It reads a playbook only when the job in front of it calls for one,
so the playbooks can be as detailed as the work needs without crowding every prompt.

## How a playbook is written

Start from `TEMPLATE.md`. The parts, in order:

1. **When to use it**: one or two lines an agent can match against its task. If this is vague, the playbook is never loaded.
2. **What good looks like**: 2 or 3 real examples you approved, pasted whole. Examples teach more than adjectives.
3. **The steps**: numbered, in the order they are done.
4. **Hard rules**: the short list of things that are never done. Each one came from a correction.
5. **The check before handing over**: what the agent tests on its own work, and what a script tests where a script can.
6. **Learned**: a dated log. Every correction you make lands here as one line, the same day.

## How a playbook stays alive

- Your correction goes into the playbook the day you make it, in your own words, with the date.
- When the same correction shows up twice, promote it: from the log to a hard rule, and from a hard rule to a script with a test.
- Once a month, read the log and fold it into the steps. A playbook that only grows at the bottom stops being read.
- One writer per playbook at a time. Two agents editing the same file in one run is how a correction gets lost.
