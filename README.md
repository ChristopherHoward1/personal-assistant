# PDE — Personal Decision Engine

A local-first CLI tool that uses Claude to help plan your week. Tasks and plans
are stored in SQLite. The agent uses Claude (via Anthropic API) with tool calling
to gather context about your workload before generating a plan.

## Status: V0 — Working Prototype

What exists today:
- Task CRUD (add, list, mark done)
- Agentic weekly planning via Claude (tool-calling loop)
- Feedback logging (adherence, satisfaction, overload)
- Plan history with feedback scores
- SQLite persistence
- Tests for service layer

What does **not** exist yet:
- Annotations (busy weeks, constraints)
- Weekly summaries
- Preference extraction / learning
- Structured output validation / repair
- Calendar integration

## Harsh Self-Critique

The [full V1 spec](#v1-spec-notes) proposes 8 database tables, 5 milestones,
preference extraction, annotations, summaries, and an LLM repair pipeline.
Here's what's wrong with that plan:

1. **The spec is a V3, not a V1.** A real V1 is: add tasks, generate a plan,
   log if it worked. That's what exists now. Ship it, use it for 3 weeks,
   *then* decide what's missing.

2. **DeepSeek-R1 via Ollama was the wrong call.** R1 is a reasoning model that
   needs 30+ GB of RAM to run locally and is notoriously bad at structured
   output. Claude Haiku via API is faster, cheaper, better at tool calling,
   and already working here.

3. **The schema is over-engineered.** `decision_requests`,
   `decision_context_snapshots`, `decision_options`, `decision_outcomes` — four
   tables to represent "I made a plan and it went okay." The current schema
   (tasks, plans, feedback) does the same job in three tables.

4. **"Preference extraction" in V1 is scope creep.** You have zero weeks of
   feedback data. Extracting preferences from nothing is architecture
   astronautics. Collect 8+ weeks of feedback first, then look for patterns.

5. **The structured output repair pipeline solves the wrong problem.** Claude's
   tool calling already returns structured JSON. The spec's parse → validate →
   repair → retry pipeline is needed for models that don't natively support
   tool use. Claude does. Skip it.

6. **"Build structured memory for future ML models" is a hope, not a feature.**
   V1 should close the loop on: plan → do → reflect → plan better. Everything
   else is premature.

## What V1 Should Actually Be

The working code today, plus:
- [ ] **Annotations** — mark weeks with constraints ("traveling Mon–Tue",
  "heavy meetings Thursday"). Feeds into the planning prompt.
- [ ] **Weekly summary** — after logging feedback, generate a short retrospective.
  Stored for the agent to reference in future plans.
- [ ] That's it.

Everything else (preferences, Alembic migrations, provider abstraction,
Ollama support) belongs in V2+ after you've used this daily for a month.

## Setup

```bash
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

### Generate a weekly plan

```bash
pde plan                        # plans for next Monday
pde plan --date 2026-03-23      # plan a specific week
```

The agent will:
1. Retrieve your open tasks
2. Check past plans and feedback
3. Assess the week's context
4. Produce a prioritized plan with defer recommendations and overload risk

### Log feedback

After the week, rate how the plan went:

```bash
pde feedback 1
```

You'll be prompted for adherence (1–5), satisfaction (1–5), overload (1–5),
and optional notes. This feedback informs future plans.

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
  db.py         SQLite models (tasks, plans, feedback)
  services.py   Business logic (CRUD, plan storage, feedback)
  agent.py      Agentic planning loop (Anthropic SDK + tool calling)
  cli.py        Typer CLI with Rich output
```

The agent has three tools it can call autonomously:
- `get_open_tasks` — query tasks by status/category/due date
- `get_recent_plans` — fetch past plans with feedback scores
- `get_week_context` — get date info for the planning week

## Testing

```bash
pytest
```

## V1 Spec Notes

The full spec is preserved in `docs/v1-spec.md` for reference. It contains
good ideas for V2+, but the current implementation intentionally deviates
from it in favor of shipping something usable first.
