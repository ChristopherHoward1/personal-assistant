# PDE — Personal Decision Engine

An AI-powered weekly planner that runs on your computer. Tell it what's on your
plate in plain English, and it builds you a realistic plan for the week. Track
what got done, and it gets smarter over time.

---

## Installation (One-Time Setup)

You'll need to open **Terminal** (on Mac: press `Cmd + Space`, type "Terminal",
hit Enter). Then paste these commands one at a time.

### Step 1: Get the code

If someone shared this folder with you, open Terminal and navigate to it:

```bash
cd ~/Documents/personal\ assistant
```

### Step 2: Set up Python

```bash
python3 -m venv .venv
```

This creates an isolated Python environment. You only do this once.

### Step 3: Activate the environment

```bash
source .venv/bin/activate
```

You'll see `(.venv)` appear at the start of your terminal line. This means
it's working. **You need to run this command every time you open a new
Terminal window.**

### Step 4: Install PDE

```bash
pip install -e ".[dev]"
```

### Step 5: Add your API key

PDE uses Claude (an AI) to understand your input and make plans. You need a
key from [console.anthropic.com](https://console.anthropic.com/). Once you
have it, create a file called `.env`:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

Replace `sk-ant-your-key-here` with your actual key.

### You're done!

Test that it works:

```bash
pde task list
```

You should see "No tasks found." — that means everything is set up correctly.

---

## How to Use It

### The only command you really need to know

```bash
pde quick "..."
```

Just describe what's going on in your own words:

```bash
pde quick "therapy Saturday at 2pm, hand specialist at 4pm, email Alice about the project by Friday"
```

PDE figures out that therapy and the hand specialist are **events** (they
block time) and emailing Alice is a **task** (something you need to do):

```
  + Event #1: therapy (2026-03-28)
  + Event #2: hand specialist appointment (2026-03-28)
  + Task #1:  Send Alice email about project update (due 2026-03-27)
```

More examples:

```bash
pde quick "team offsite next Tue through Thu, prep slides by Monday"
pde quick "dentist Wednesday 9am, pick up dry cleaning"
pde quick "finish code review by Friday, grocery shopping this weekend"
```

You can run this as many times as you want throughout the week. Just dump
whatever comes to mind.

### Generate a weekly plan

When you're ready to see your week laid out:

```bash
pde plan
```

The AI reviews everything you've added — tasks, events, constraints — along
with how past weeks went, and gives you a prioritized plan:

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

You can also add a note to give the planner extra context:

```bash
pde plan --note "light week, want to focus on deep work"
```

### Check off tasks as you finish them

```bash
pde task list          # see all your tasks
pde task done 3        # mark task #3 as done (use the ID from the list)
```

### End-of-week review

At the end of the week, tell PDE what actually happened:

```bash
pde feedback 1         # the number is the plan ID (shown when you created it)
```

It walks you through each task:

```
Priority tasks — did you complete them?
  Write quarterly report (#1)? [y/N]: y
  Review PR backlog (#3)? [y/N]: n

Adherence (how closely did you follow the plan?): 4
Satisfaction (how good was the plan?): 4
Overload (how overwhelmed were you?): 2
Notes (optional): Report took longer than expected

Feedback logged.
  Tasks completed: 1/2
```

Type `y` or `n` for each task, then rate the week 1–5 on three scales.
This takes about 30 seconds and helps future plans be more realistic.

### See your history

```bash
pde history
```

Shows your past plans and how they went.

---

## Your Weekly Routine

```
Monday morning:
  pde quick "..."              ← brain dump everything on your plate
  pde plan                     ← get a structured plan

During the week:
  pde quick "..."              ← add things as they come up
  pde task done 5              ← check off tasks as you go

End of week:
  pde feedback 1               ← quick review of what got done

Next Monday:
  pde plan                     ← new plan, informed by last week
```

That's it. Four commands cover 95% of usage: `quick`, `plan`, `task done`,
and `feedback`.

---

## All Available Commands

| Command | What it does |
|---|---|
| `pde quick "..."` | Add tasks and events in plain English |
| `pde plan` | Generate a weekly plan |
| `pde plan --note "..."` | Plan with extra context |
| `pde feedback 1` | Review how plan #1 went |
| `pde task list` | See all your tasks |
| `pde task done 3` | Mark task #3 as done |
| `pde task add "..." --due 2026-03-27` | Add a task manually (with a deadline) |
| `pde annotation list` | See your events and constraints |
| `pde history` | See past plans and feedback |

---

## Troubleshooting

**"command not found: pde"**
You need to activate the environment first:
```bash
cd ~/Documents/personal\ assistant
source .venv/bin/activate
```

**"Could not resolve authentication method"**
Your API key isn't set. Check that your `.env` file exists and has your key:
```bash
cat .env
```
It should show `ANTHROPIC_API_KEY=sk-ant-...`

**"No tasks found"**
That's fine! It just means you haven't added anything yet. Run `pde quick "..."`
to get started.

---

## For Developers

### Architecture

```
src/pde/
  db.py         SQLite models (tasks, plans, feedback, annotations)
  services.py   Business logic (CRUD, stats, plan storage, feedback)
  agent.py      Agent loops — planning + quick capture (Anthropic SDK)
  cli.py        Typer CLI with Rich output
```

4 tables: tasks, plans, feedback, annotations.

2 agent loops, same pattern (tool-calling loop with Claude Haiku):

| Agent | Tools | Purpose |
|---|---|---|
| **Planner** | `get_week_context`, `get_annotations`, `get_open_tasks`, `get_recent_plans`, `submit_plan` | Generate a weekly plan from tasks, constraints, and history |
| **Quick capture** | `create_task`, `create_annotation` | Parse natural language into tasks and events |

### Data storage

Your data lives in `~/.pde/pde.db` — outside the project directory. This
means:
- Each user on a machine gets their own database automatically
- Re-cloning or moving the project doesn't touch your data
- The database never gets accidentally committed to git

To use a custom location:
```bash
export PDE_DATA_DIR=/path/to/your/data
```

To start fresh, just delete the file:
```bash
rm ~/.pde/pde.db
```

### Configuration

| Env var | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `PDE_MODEL` | `claude-haiku-4-5-20251001` | Model used for all agent calls |
| `PDE_DATA_DIR` | `~/.pde` | Directory for the SQLite database |

### Testing

```bash
source .venv/bin/activate
pytest -v
```

26 tests covering: task CRUD, plan storage, feedback (with task results),
week stats, annotations (overlap filtering, partial overlap, deletion).

### Data Model: Designed for Future Learning

Every interaction with PDE generates structured data that accumulates over
time. The SQLite database isn't just storage — it's a training dataset
being built through normal use.

| Table | What it records | ML signal |
|---|---|---|
| **tasks** | What you committed to, estimated time, priority, category, whether it got done | Task completion patterns, estimation accuracy |
| **plans** | Structured plan JSON (priority tasks, deferred tasks, strategy, overload risk) + full agent interaction trace | What plans you accepted, how many tasks per week works |
| **feedback** | Adherence, satisfaction, overload scores + per-task completion booleans | Your actual capacity vs. planned capacity, what overload looks like |
| **annotations** | Constraints per week (travel, meetings, deadlines) | How constraints affect completion rates and satisfaction |

With 8+ weeks of data, this enables: estimation calibration (are your time
estimates accurate?), overload prediction (will this plan overwhelm you?),
deferral pattern detection (you've put off X three times), category-based
capacity modeling, and day-of-week effect analysis.

The system doesn't need to change to support this. The structured data from
plans, feedback, and task results is already in the right shape. When enough
weeks accumulate, a Jupyter notebook with pandas can produce the first
insights in an hour. Predictive features get folded back in as heuristics,
and eventually a lightweight model replaces hand-tuned scoring.

## What's Next

- [ ] **Weekly summary** — auto-generate a retrospective after feedback
- [ ] **Apple Calendar sync** — push events/time blocks to Calendar.app
- [ ] **Simple UI** — lightweight web interface for input and feedback
