# PDE — Personal Decision Engine

A local-first CLI tool that uses Claude Haiku to help you organize your week.
Add tasks and events in plain English, generate a weekly plan, and track what
actually got done. Everything is stored in SQLite on your machine.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a `.env` file (gitignored):
```
ANTHROPIC_API_KEY=sk-ant-...
```

## How to Use It

### 1. Dump everything into quick capture

The fastest way to get things into PDE. Just describe your week:

```bash
pde quick "therapy Saturday at 2pm, hand specialist at 4pm, email Alice about the project by Friday"
```

```
  + Event #1: therapy (2026-03-28)
  + Event #2: hand specialist appointment (2026-03-28)
  + Task #1:  Send Alice email about project update (due 2026-03-27)
```

The agent figures out what's a task (something you need to do) vs. an event
(something that blocks time) and creates the right thing. Relative dates like
"Saturday" and "Friday" are resolved automatically.

```bash
pde quick "team offsite next Tue through Thu, prep slides by Monday"
pde quick "dentist Wednesday 9am, pick up dry cleaning, finish code review by EOD Friday"
```

### 2. Manage tasks directly (when you want precision)

```bash
pde task add "Write quarterly report" --priority 1 --due 2026-03-27 --minutes 120 --category work
pde task list
pde task list --status open --category work
pde task done 1
```

### 3. Annotate your week

Flag constraints so the planner knows what's going on:

```bash
pde annotation add "traveling" --start 2026-03-23 --end 2026-03-25
pde annotation add "deadline: quarterly report" --start 2026-03-27
pde annotation list
pde annotation list --week 2026-03-23
pde annotation remove 1
```

(Quick capture also creates annotations automatically for events and
appointments.)

### 4. Generate a weekly plan

```bash
pde plan                                  # this week (Mon-Wed) or next week (Thu-Sun)
pde plan --date 2026-03-23               # plan a specific week
pde plan --note "light week, deep work"  # give the planner extra context
```

The agent gathers your open tasks, checks for annotations and constraints,
reviews past plans and feedback, then delivers a structured plan:

```
╭──────────────── Week Plan #1 (2026-03-23 → 2026-03-29) ─────────────────╮
│ Priority Tasks                                                           │
│  1. Write quarterly report (due Fri 3/27) — 2 hours                     │
│  2. Review PR backlog (due Wed 3/25) — 1 hour                           │
│                                                                          │
│ Constraints                                                              │
│  • Tue 3/24: Back-to-back meetings all day                               │
│  • Sat 3/28: Therapy at 2pm, hand specialist at 4pm                     │
│                                                                          │
│ Deferred                                                                 │
│  • Grocery shopping → next week (no time pressure)                       │
╰──────────────────────────────────────────────────────────────────────────╯

  Overload risk: low
  Priority tasks: 2  |  Deferred: 1
```

### 5. Close the loop with feedback

After the week, tell PDE what actually happened:

```bash
pde feedback 1
```

```
Priority tasks — did you complete them?
  Write quarterly report (#1)? [y/N]: y
  Review PR backlog (#3)? [y/N]: n

Adherence (how closely did you follow the plan?): 4
Satisfaction (how good was the plan?): 4
Overload (how overwhelmed were you?): 2
Notes (optional): Report took longer than expected, PR review slipped

Feedback logged.
  Scores: adherence=4 satisfaction=4 overload=2
  Tasks completed: 1/2
```

Completed tasks are automatically marked done. The feedback — scores and
task-level results — feeds into future plans so the agent learns what's
realistic for you.

### 6. Review past plans

```bash
pde history             # last 5 plans
pde history --limit 10  # last 10
```

## Typical Weekly Workflow

```
Monday morning:
  pde quick "..."              ← dump everything on your mind
  pde plan                     ← get a structured plan for the week

During the week:
  pde quick "..."              ← add things as they come up
  pde task done 5              ← check off tasks as you finish them

End of week:
  pde feedback 1               ← review what got done, rate the plan

Next Monday:
  pde plan                     ← new plan, informed by last week's feedback
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `PDE_MODEL` | `claude-haiku-4-5-20251001` | Model used for all agent calls |

All agent calls (planning, quick capture) use Claude Haiku. Fast, cheap,
and good enough for task parsing and weekly planning.

## Architecture

```
src/pde/
  db.py         SQLite models (tasks, plans, feedback, annotations)
  services.py   Business logic (CRUD, stats, plan storage, feedback)
  agent.py      Agent loops — planning + quick capture (Anthropic SDK)
  cli.py        Typer CLI with Rich output
```

**4 tables:** tasks, plans, feedback, annotations.

**2 agent loops**, same pattern (tool-calling loop → structured output):

| Agent | Tools | Purpose |
|---|---|---|
| **Planner** | `get_week_context`, `get_annotations`, `get_open_tasks`, `get_recent_plans`, `submit_plan` | Generate a weekly plan from your tasks, constraints, and history |
| **Quick capture** | `create_task`, `create_annotation` | Parse natural language into tasks and events |

## Testing

```bash
source .venv/bin/activate
pytest -v
```

26 tests covering: task CRUD, plan storage, feedback (with task results),
week stats, annotations (overlap filtering, partial overlap, deletion).

## Data Model: Designed for Future Learning

Every interaction with PDE generates structured data that accumulates over
time. The SQLite database isn't just persistence — it's a training dataset
being built through normal use.

### What gets captured

| Table | What it records | ML signal |
|---|---|---|
| **tasks** | What you committed to, estimated time, priority, category, whether it got done | Task completion patterns, estimation accuracy |
| **plans** | Structured plan JSON (priority tasks, deferred tasks, strategy, overload risk) + full agent interaction trace | What plans you accepted, how many tasks per week works |
| **feedback** | Adherence, satisfaction, overload scores + per-task completion booleans | Your actual capacity vs. planned capacity, what overload looks like |
| **annotations** | Constraints per week (travel, meetings, deadlines) | How constraints affect completion rates and satisfaction |

### What becomes possible with 8+ weeks of data

**Estimation calibration** — Compare `estimated_minutes` at task creation
against actual completion patterns. If you consistently finish 60-minute tasks
but not 120-minute ones, the planner should learn your real throughput.

**Overload prediction** — Correlate `overload_score` with the number of
priority tasks, total estimated minutes, annotation density, and high-priority
count. A simple logistic regression could flag "this plan will overwhelm you"
before Monday.

**Deferral patterns** — Track which tasks get deferred across multiple plans.
"You've deferred X three times — either do it, delegate it, or drop it" is a
rule that writes itself from the data.

**Category-based capacity** — Your capacity for deep work (category=work,
high priority) vs. errands (category=personal, low priority) may be very
different. The data separates these naturally.

**Day-of-week effects** — Annotations capture when constraints cluster.
Combined with feedback, this reveals patterns like "plans that load Tuesday
heavily always score low on satisfaction."

### How to get there

The current system doesn't need to change. The structured data from
`plan_json`, `task_results_json`, and feedback scores is already in the right
shape. When enough weeks accumulate:

1. Export with `sqlite3 pde.db` — it's all local, no API needed
2. A Jupyter notebook with pandas can produce the first insights in an hour
3. Predictive features get folded back into `get_week_stats` as new heuristics
4. Eventually, a lightweight model replaces the hand-tuned scoring

The key insight: **you don't build the ML system first and hope for data.
You build the data collection into normal use and let the models come later.**

## What's Next

- [ ] **Weekly summary** — auto-generate a retrospective after feedback
- [ ] **Apple Calendar sync** — push events/time blocks to Calendar.app
- [ ] **Simple UI** — lightweight web interface for input and feedback
