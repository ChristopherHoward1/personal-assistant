# PDE — Personal Decision Engine

A local-first CLI tool that uses Claude to help plan your week. Tasks and plans
are stored in SQLite. The agent uses Claude (via Anthropic API) with tool calling
to gather context about your workload before generating a structured plan.

## Status: V1 — Core Loop Complete

What works today:
- Task CRUD (add, list, mark done)
- Annotations (tag weeks with constraints: travel, deadlines, busy days)
- Agentic weekly planning via Claude with structured output (`submit_plan` tool)
- Task-level feedback (walk through each priority task, mark done/not done)
- Workload stats (agent sees task counts, estimated hours, due dates at a glance)
- Plan history with feedback scores and task-level results
- User notes on plans (`--note "focus on deep work"`)
- SQLite persistence (4 tables: tasks, plans, feedback, annotations)
- 26 tests covering services layer

What does **not** exist yet:
- Weekly summaries
- Preference extraction / learning
- Calendar integration (Apple Calendar via osascript — planned for V2)

## Harsh Self-Critique

The [original spec](#v1-spec-notes) proposed 8 database tables, 5 milestones,
preference extraction, summaries, and an LLM repair pipeline.
Here's what was wrong with that plan:

1. **The spec was a V3, not a V1.** A real V1 is: add tasks, generate a plan,
   log if it worked. That's what exists now.

2. **DeepSeek-R1 via Ollama was the wrong call.** R1 is a reasoning model that
   needs 30+ GB of RAM to run locally and is notoriously bad at structured
   output. Claude Haiku via API is faster, cheaper, better at tool calling,
   and already working here.

3. **The schema was over-engineered.** `decision_requests`,
   `decision_context_snapshots`, `decision_options`, `decision_outcomes` — four
   tables to represent "I made a plan and it went okay." The current schema
   (tasks, plans, feedback, annotations) does the same job in four tables.

4. **"Preference extraction" in V1 is scope creep.** Collect 8+ weeks of
   feedback data first, then look for patterns.

5. **The structured output repair pipeline solves the wrong problem.** Claude's
   tool calling (`submit_plan`) returns structured JSON natively. No parsing,
   no repair, no retry needed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a `.env` file (already gitignored):
```
ANTHROPIC_API_KEY=sk-ant-...
```

Or export directly:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Manage tasks

```bash
pde task add "Write quarterly report" --priority 1 --due 2026-03-27 --minutes 120 --category work
pde task add "Grocery shopping" --priority 3 --category personal
pde task list
pde task list --status open --category work
pde task done 1
```

### Annotate your week

Flag constraints so the planner knows what's going on:

```bash
pde annotation add "traveling" --start 2026-03-23 --end 2026-03-25
pde annotation add "deadline: quarterly report" --start 2026-03-27
pde annotation list
pde annotation list --week 2026-03-23    # annotations overlapping this week
pde annotation remove 1
```

### Generate a weekly plan

```bash
pde plan                                  # this week (Mon-Wed) or next week (Thu-Sun)
pde plan --date 2026-03-23               # plan a specific week
pde plan --note "light week, deep work"  # give the planner extra context
```

The agent will:
1. Get a workload snapshot (task counts, estimated hours, due dates)
2. Check for annotations (travel, deadlines, constraints)
3. Retrieve your open tasks
4. Review past plans and feedback
5. Call `submit_plan` with a structured plan:
   - Priority tasks (with reasons)
   - Deferred tasks (with reasons)
   - Weekly strategy
   - Overload risk (low/medium/high)

### Log feedback

After the week, review how the plan went:

```bash
pde feedback 1
```

If the plan has structured data, you'll walk through each priority task:
```
Priority tasks — did you complete them?
  Write quarterly report (#3)? [y/N]
  Review PR backlog (#5)? [y/N]
```

Completed tasks are automatically marked done. Then you rate:
- Adherence (1–5): how closely you followed the plan
- Satisfaction (1–5): how good the plan was
- Overload (1–5): how overwhelmed you were

This feedback — including task-level results — is visible to the agent
when planning future weeks.

### View history

```bash
pde history             # last 5 plans
pde history --limit 10  # last 10
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `PDE_MODEL` | `claude-haiku-4-5-20251001` | Model to use for planning |

## Architecture

```
src/pde/
  db.py         SQLite models (tasks, plans, feedback, annotations)
  services.py   Business logic (CRUD, stats, plan storage, feedback)
  agent.py      Agentic planning loop (Anthropic SDK + tool calling)
  cli.py        Typer CLI with Rich output
```

### Agent tools

The planning agent has five tools it can call:

| Tool | Purpose |
|---|---|
| `get_week_context` | Workload snapshot: task counts, estimated hours, high-priority count |
| `get_annotations` | Constraints overlapping the planning week |
| `get_open_tasks` | Full task list, filterable by category/due date |
| `get_recent_plans` | Past plans with feedback scores and task-level results |
| `submit_plan` | Deliver the structured plan (required to finish) |

### Planning loop

```
User runs: pde plan
  → Agent calls get_week_context (workload dashboard)
  → Agent calls get_annotations (constraints)
  → Agent calls get_open_tasks (full list)
  → Agent optionally calls get_recent_plans (past feedback)
  → Agent reasons about priorities and capacity
  → Agent calls submit_plan with structured output
  → Plan is stored (text + JSON + interaction trace)
  → User sees the plan + overload risk
```

### Feedback loop

```
User runs: pde feedback <plan-id>
  → Walk through each priority task (complete? y/n)
  → Completed tasks marked done in DB
  → Rate adherence / satisfaction / overload
  → Task results + scores stored
  → Future plans see what worked and what didn't
```

## Testing

```bash
source .venv/bin/activate
pytest -v
```

26 tests covering: task CRUD, plan storage, feedback (with task results),
week stats, annotations (overlap filtering, partial overlap, deletion).

## V1 Spec Notes

The original spec is preserved in `docs/v1-spec.md` for reference. It contains
good ideas for V2+, but the current implementation intentionally deviates
from it in favor of shipping something usable first.

## What's next

- [ ] **Weekly summary** — after feedback, generate a short retrospective
- [ ] **Apple Calendar sync** — push time blocks via `osascript` (`--sync-calendar` flag)
- [ ] **Use it for 2 real weeks** — then decide what V2 needs based on actual friction
