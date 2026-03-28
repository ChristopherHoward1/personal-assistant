# PDE — Technical Documentation

## Architecture

```
                     User
                       |
                       v
              ┌────────────────┐
              │   CLI (cli.py) │  Typer + Rich
              │                │  Commands, prompts, formatting
              └───────┬────────┘
                      |
           ┌──────────┴──────────┐
           v                     v
   ┌───────────────┐    ┌───────────────┐
   │ Planning Agent │    │  Quick Agent  │  agent.py
   │ (10 steps max) │    │ (6 steps max) │  Claude tool-calling loops
   └───────┬───────┘    └───────┬───────┘
           |                     |
           v                     v
   ┌──────────────────────────────────┐
   │       Services (services.py)     │  Business logic, CRUD, stats
   └───────────────┬──────────────────┘
                   |
                   v
   ┌──────────────────────────────────┐
   │        Database (db.py)          │  SQLModel + SQLite
   │        ~/.pde/pde.db             │  4 tables
   └──────────────────────────────────┘
```

### Design principles

- **LLM is the orchestrator, not a formatter.** The agent decides what context
  to fetch and when. It calls tools (DB queries) autonomously.
- **Structured output via tool calling.** The planning agent must call
  `submit_plan` to finish. No JSON parsing, no repair pipeline. Claude's
  tool-use format guarantees structure.
- **Data stays local.** SQLite at `~/.pde/pde.db`. API calls go to Anthropic
  for reasoning only — no user data is stored remotely.
- **Feedback closes the loop.** Every plan gets scored. Scores feed into
  future plans via `get_recent_plans`.

---

## Database Schema

All models use SQLModel (Pydantic + SQLAlchemy). Database location:
`~/.pde/pde.db` (configurable via `PDE_DATA_DIR`).

### tasks

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER | auto | Primary key |
| `title` | VARCHAR | — | Required |
| `description` | VARCHAR | NULL | |
| `category` | VARCHAR | NULL | e.g. "work", "personal", "health" |
| `priority` | INTEGER | 3 | 1 = highest, 5 = lowest |
| `estimated_minutes` | INTEGER | NULL | |
| `due_date` | DATE | NULL | |
| `status` | VARCHAR | "open" | "open", "done", "deferred" |
| `created_at` | DATETIME | now() | |
| `updated_at` | DATETIME | now() | Updated on status change |

### plans

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER | auto | Primary key |
| `week_start` | DATE | — | Monday of the planned week |
| `week_end` | DATE | — | Computed: week_start + 6 days |
| `interaction_trace` | VARCHAR | NULL | JSON: full agent tool-call trace |
| `plan_json` | VARCHAR | NULL | JSON: structured output from `submit_plan` |
| `plan_text` | VARCHAR | NULL | Markdown: human-readable plan |
| `model_name` | VARCHAR | "claude-haiku-4-5-20251001" | |
| `created_at` | DATETIME | now() | |

**`plan_json` schema** (when populated by `submit_plan`):

```json
{
  "priority_tasks": [
    {"task_id": 1, "title": "Write report", "reason": "Due Friday"}
  ],
  "defer_tasks": [
    {"task_id": 2, "title": "Groceries", "reason": "No time pressure"}
  ],
  "strategy": "Focus on report Wed-Thu, clear small tasks Monday.",
  "overload_risk": "low",
  "plan_summary": "Markdown summary of the full plan..."
}
```

**`interaction_trace` schema**:

```json
[
  {
    "step": 0,
    "role": "assistant",
    "stop_reason": "tool_use",
    "content": [{"type": "tool_use", "name": "get_week_context", "input": {...}}]
  },
  {
    "step": 0,
    "role": "tool",
    "tool_name": "get_week_context",
    "input": {"week_start": "2026-03-23"},
    "output_preview": "{\"open_task_count\": 5, ...}"
  }
]
```

### feedback

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER | auto | Primary key |
| `plan_id` | INTEGER | — | Foreign key → plans.id |
| `adherence` | INTEGER | — | 1-5: how closely user followed the plan |
| `satisfaction` | INTEGER | — | 1-5: how good the plan was |
| `overload` | INTEGER | — | 1-5: how overwhelmed (1=under, 5=crushed) |
| `notes` | VARCHAR | NULL | Free-text reflection |
| `task_results_json` | VARCHAR | NULL | JSON: per-task completion |
| `created_at` | DATETIME | now() | |

**`task_results_json` schema**:

```json
[
  {"task_id": 1, "title": "Write report", "completed": true},
  {"task_id": 3, "title": "Review PRs", "completed": false}
]
```

### annotations

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER | auto | Primary key |
| `start_date` | DATE | — | |
| `end_date` | DATE | — | Same as start for single-day events |
| `label` | VARCHAR | — | e.g. "traveling", "deadline", "therapy" |
| `description` | VARCHAR | NULL | Details like time, location |
| `created_at` | DATETIME | now() | |

---

## Agent System

Both agents use the same pattern: a tool-calling loop with Claude Haiku via
the Anthropic SDK. The agent sends messages, Claude responds with tool calls
or text, tools are executed, results are fed back, and the loop continues
until termination.

### Planning Agent

**File:** `agent.py` → `run_planning_agent(week_start, note=None)`

**Model:** `PDE_MODEL` env var or `claude-haiku-4-5-20251001`

**Max steps:** 10

**System prompt instructs the agent to:**
1. Call `get_week_context` for a workload snapshot
2. Call `get_annotations` for constraints
3. Call `get_open_tasks` for the full task list
4. Optionally call `get_recent_plans` to review past feedback
5. Reason about capacity (15-20 hours/week baseline)
6. Call `submit_plan` to deliver the structured plan

**Termination:** The loop ends when the agent calls `submit_plan` (structured
output extracted from tool input) or when `stop_reason == "end_turn"` (fallback:
raw text extracted as plan_text, plan_json is None).

#### Planning tools

**get_open_tasks**
```
Input:  {category?: string, due_before?: ISO date}
Output: [{id, title, description, category, priority, estimated_minutes, due_date, status}]
```

**get_recent_plans**
```
Input:  {limit?: int (default 3)}
Output: [{id, week_start, week_end, plan_text, feedback: {adherence, satisfaction, overload, notes, task_results?}}]
```

**get_annotations**
```
Input:  {start_date: ISO date, end_date: ISO date}  (both required)
Output: [{id, label, description, start_date, end_date}]
```

**get_week_context**
```
Input:  {week_start: ISO date}  (required)
Output: {week_start, week_end, today, open_task_count, due_this_week_count,
         high_priority_count, total_estimated_minutes, week_estimated_minutes}
```

**submit_plan** (terminal)
```
Input: {
  priority_tasks: [{task_id: int, title: str, reason: str}],  (max 7)
  defer_tasks:    [{task_id: int, title: str, reason: str}],
  strategy:       str,  (1-3 sentences)
  overload_risk:  "low" | "medium" | "high",
  plan_summary:   str   (markdown)
}
Output: (not executed — extracted directly in the agent loop)
```

**Return value:**
```python
{
    "plan_text": str,       # from submit_plan.plan_summary
    "plan_json": dict,      # full submit_plan input
    "trace": list[dict],    # step-by-step interaction log
}
```

### Quick Capture Agent

**File:** `agent.py` → `run_quick_agent(user_input)`

**Max steps:** 6

**System prompt injects today's date** and instructs the agent to:
- Parse natural language into tasks and annotations
- Appointments/events → `create_annotation`
- Action items/to-dos → `create_task`
- Resolve relative dates ("Saturday", "next week", "Friday")
- Put specific times in annotation descriptions
- Set priority 2 for explicit deadlines, 3-4 for casual items

**Termination:** Loop ends when `stop_reason == "end_turn"`. The agent's
final text message is returned as `summary`.

#### Quick capture tools

**create_task**
```
Input:  {title: str, due_date?: ISO date, priority?: 1-5, estimated_minutes?: int,
         category?: str, description?: str}
Output: {type: "task", id: int, title: str, due_date: str?}
```

**create_annotation**
```
Input:  {label: str, start_date: ISO date, end_date: ISO date, description?: str}
Output: {type: "annotation", id: int, label: str, start_date: str}
```

**Return value:**
```python
{
    "created": [
        {"type": "task", "id": 1, "title": "...", "due_date": "..."},
        {"type": "annotation", "id": 1, "label": "...", "start_date": "..."},
    ],
    "summary": str,  # agent's confirmation text
}
```

---

## Services Layer

All functions in `services.py`. Each opens its own database session.

### Task CRUD

```python
add_task(title, description=None, category=None, priority=3,
         estimated_minutes=None, due_date=None) → Task
```
Creates and persists a new task.

```python
list_tasks(status=None, category=None) → list[Task]
```
Returns tasks ordered by priority (ascending), then due_date. Filters are
optional and combinable.

```python
complete_task(task_id: int) → Task
```
Sets `status="done"`, updates `updated_at`. Raises `ValueError` if not found.

### Week Stats

```python
get_week_stats(week_start: date) → dict
```
Computes workload snapshot for the agent:
- Counts open tasks, tasks due this week, high-priority tasks (priority <= 2)
- Sums estimated minutes (total and week-only)
- Returns dates as ISO strings

### Plan Management

```python
save_plan(week_start, plan_text, plan_json=None,
          interaction_trace=None, model_name="claude-haiku-4-5-20251001") → Plan
```
Saves a plan. Computes `week_end = week_start + 6 days`.

```python
get_plan(plan_id: int) → Optional[Plan]
```
Retrieve a single plan by ID.

```python
get_recent_plans(limit: int = 3) → list[dict]
```
Returns recent plans with feedback joined. Each entry includes the full
feedback record (scores + task_results) if one exists.

### Annotations

```python
add_annotation(start_date, end_date, label, description=None) → Annotation
```

```python
list_annotations(from_date=None, to_date=None) → list[Annotation]
```
If both dates provided, returns annotations **overlapping** the range:
`annotation.start_date <= to_date AND annotation.end_date >= from_date`.
Ordered by start_date.

```python
delete_annotation(annotation_id: int) → None
```
Raises `ValueError` if not found.

### Feedback

```python
log_feedback(plan_id, adherence, satisfaction, overload,
             notes=None, task_results=None) → Feedback
```
Validates plan exists. Serializes `task_results` list as JSON if provided.
Raises `ValueError` if plan not found.

---

## CLI Commands

Entry point: `pde = pde.cli:app` (Typer application).

Environment is loaded from `.env` in the project root on import
(`python-dotenv` with `override=True`).

### pde quick

```
pde quick TEXT
```

Parse natural language into tasks and events. No flags needed.

### pde task add

```
pde task add TITLE [--priority/-p INT] [--due/-d DATE] [--minutes/-m INT]
                   [--category/-c STR] [--desc STR]
```

- `priority`: 1-5 (default 3)
- `due`: ISO date (YYYY-MM-DD)
- `minutes`: estimated time

### pde task list

```
pde task list [--status/-s STR] [--category/-c STR]
```

Rich table output sorted by priority.

### pde task done

```
pde task done TASK_ID
```

### pde annotation add

```
pde annotation add LABEL --start/-s DATE [--end/-e DATE] [--desc STR]
```

`end` defaults to `start` if omitted (single-day event).

### pde annotation list

```
pde annotation list [--week/-w DATE]
```

If `--week` provided, filters to annotations overlapping that Monday-Sunday.

### pde annotation remove

```
pde annotation remove ANNOTATION_ID
```

### pde plan

```
pde plan [--date/-d DATE] [--note/-n STR]
```

- Default date: this Monday (Mon-Wed) or next Monday (Thu-Sun)
- Note is passed to the agent as user context

### pde feedback

```
pde feedback PLAN_ID
```

Interactive. If plan has structured data (`plan_json`), walks through each
priority task asking y/n for completion. Completed tasks are auto-marked
done in the tasks table. Then prompts for adherence, satisfaction, overload
(1-5 each) and optional notes.

### pde history

```
pde history [--limit/-n INT]
```

Default: last 5 plans.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key for Claude |
| `PDE_MODEL` | `claude-haiku-4-5-20251001` | Model for all agent calls |
| `PDE_DATA_DIR` | `~/.pde` | Directory containing `pde.db` |

`.env` is loaded from the project root (`src/pde/../../.env`) with
`override=True` so it takes precedence over shell environment.

The database directory is created automatically on first import of `pde.db`
if it doesn't exist.

---

## Data Flow

### Plan Generation

```
pde plan [--date D] [--note N]
  │
  ├─ Resolve week_start (this/next Monday)
  ├─ Call run_planning_agent(week_start, note)
  │    │
  │    ├─ Step 1: Agent calls get_week_context
  │    │    └─ services.get_week_stats → {counts, minutes}
  │    ├─ Step 2: Agent calls get_annotations
  │    │    └─ services.list_annotations(from, to) → [{label, dates}]
  │    ├─ Step 3: Agent calls get_open_tasks
  │    │    └─ services.list_tasks(status="open") → [{task}]
  │    ├─ Step 4: (optional) Agent calls get_recent_plans
  │    │    └─ services.get_recent_plans() → [{plan + feedback}]
  │    └─ Step 5: Agent calls submit_plan
  │         └─ Structured plan extracted from tool input
  │
  ├─ save_plan(week_start, plan_text, plan_json, trace)
  └─ Display plan in Rich panel
```

### Feedback

```
pde feedback PLAN_ID
  │
  ├─ get_plan(plan_id) → plan with plan_json
  ├─ If plan_json exists:
  │    └─ For each priority_task:
  │         ├─ Prompt: "Did you complete X? [y/N]"
  │         └─ If yes: complete_task(task_id)
  ├─ Prompt: adherence, satisfaction, overload (1-5)
  ├─ Prompt: notes (optional)
  └─ log_feedback(plan_id, scores, task_results)
```

### Quick Capture

```
pde quick "natural language input"
  │
  ├─ Call run_quick_agent(text)
  │    │
  │    ├─ Agent parses input
  │    ├─ Calls create_task for action items
  │    │    └─ services.add_task(title, due, priority, ...)
  │    ├─ Calls create_annotation for events
  │    │    └─ services.add_annotation(label, start, end, desc)
  │    └─ Ends turn with confirmation summary
  │
  └─ Display created items
```

---

## Testing

### Setup

Tests use a temporary directory for the database:

```python
os.environ["PDE_DATA_DIR"] = tempfile.mkdtemp()
```

This must be set **before** importing `pde.db` (which reads the env var at
module level to configure the engine).

### Fixture

```python
@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)
```

Every test gets a clean database. Tables are dropped and recreated between tests.

### Coverage

26 tests across 5 test classes:

| Class | Tests | What's covered |
|---|---|---|
| `TestTaskCRUD` | 8 | add, list (empty, filtered, ordered), complete, errors |
| `TestPlans` | 3 | save, list empty, list with feedback joined |
| `TestFeedback` | 3 | basic, with task_results JSON, nonexistent plan |
| `TestWeekStats` | 4 | empty stats, multi-task stats, get_plan, get_plan miss |
| `TestAnnotations` | 8 | add, single-day, range filter, no overlap, partial overlap, list all, delete, delete miss |

### Running

```bash
source .venv/bin/activate
pytest -v
```

### What's not tested

- Agent loops (would require mocking Anthropic API responses)
- CLI commands (would require click.testing or typer.testing)
- `.env` loading behavior

---

## Data Model for ML

PDE captures structured data through normal use that enables predictive
modeling after sufficient accumulation (target: 8+ weeks).

### Extraction queries

**Task completion rate by category:**
```sql
SELECT category,
       COUNT(*) as total,
       SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as completed,
       ROUND(100.0 * SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
FROM tasks
WHERE category IS NOT NULL
GROUP BY category;
```

**Estimation accuracy (planned vs. completed):**
```sql
SELECT t.title, t.estimated_minutes, t.status,
       t.created_at, t.updated_at
FROM tasks t
WHERE t.estimated_minutes IS NOT NULL
  AND t.status = 'done';
```

**Overload correlation with plan density:**
```sql
SELECT p.id, p.week_start,
       json_extract(p.plan_json, '$.overload_risk') as predicted_risk,
       json_array_length(json_extract(p.plan_json, '$.priority_tasks')) as task_count,
       f.overload as actual_overload,
       f.satisfaction
FROM plans p
JOIN feedback f ON f.plan_id = p.id
WHERE p.plan_json IS NOT NULL;
```

**Deferral frequency (tasks appearing across multiple plans):**
```sql
SELECT json_extract(value, '$.task_id') as task_id,
       json_extract(value, '$.title') as title,
       COUNT(*) as times_deferred
FROM plans p, json_each(json_extract(p.plan_json, '$.defer_tasks'))
WHERE p.plan_json IS NOT NULL
GROUP BY task_id
HAVING COUNT(*) > 1
ORDER BY times_deferred DESC;
```

**Annotation impact on satisfaction:**
```sql
SELECT p.week_start,
       (SELECT COUNT(*) FROM annotations a
        WHERE a.start_date <= p.week_end AND a.end_date >= p.week_start) as annotation_count,
       f.satisfaction, f.overload
FROM plans p
JOIN feedback f ON f.plan_id = p.id;
```

### Predictive model opportunities

| Model | Input features | Target | Minimum data |
|---|---|---|---|
| **Overload predictor** | task count, total minutes, annotation count, high-priority count | overload score (1-5) | 8 weeks |
| **Estimation calibrator** | estimated_minutes, category, priority | actual completion (bool) | 30+ tasks |
| **Deferral detector** | times deferred, priority, category, age | will-defer-again (bool) | 12 weeks |
| **Satisfaction predictor** | overload, adherence, task completion rate | satisfaction (1-5) | 8 weeks |

All features are available in the current schema. No changes needed.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typer` | >= 0.12 | CLI framework |
| `sqlmodel` | >= 0.0.22 | ORM (SQLAlchemy + Pydantic) |
| `pydantic` | >= 2.0 | Data validation (via SQLModel) |
| `anthropic` | >= 0.40 | Claude API client |
| `rich` | >= 13.0 | Terminal formatting (tables, panels, markdown) |
| `python-dotenv` | >= 1.0 | .env file loading |
| `pytest` | >= 8.0 | Testing (dev) |
| `pytest-cov` | >= 5.0 | Coverage reporting (dev) |
