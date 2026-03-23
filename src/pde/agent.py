import json
import os
from datetime import date, timedelta

import anthropic

from pde.services import list_tasks, get_recent_plans, list_annotations

TOOLS = [
    {
        "name": "get_open_tasks",
        "description": "Retrieve open tasks, optionally filtered by category or due date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. 'work', 'personal').",
                },
                "due_before": {
                    "type": "string",
                    "description": "ISO date string. Only return tasks due on or before this date.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_recent_plans",
        "description": "Retrieve recent weekly plans and their feedback scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent plans to return (default 3).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_annotations",
        "description": "Retrieve annotations (constraints, travel, deadlines, events) overlapping a date range. Always check this when planning a week.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "ISO date for range start.",
                },
                "end_date": {
                    "type": "string",
                    "description": "ISO date for range end.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_week_context",
        "description": "Get info about the planning week: start date, end date, day count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "week_start": {
                    "type": "string",
                    "description": "ISO date of the Monday to plan for.",
                },
            },
            "required": ["week_start"],
        },
    },
]

SYSTEM_PROMPT = """\
You are a personal weekly planner. Your job is to help the user plan their upcoming week.

You have tools to retrieve open tasks, past plans, and week context. Use them to understand
the user's workload, then produce a concrete weekly plan.

Rules:
- Call tools to gather context before making your plan.
- Always check for annotations — these are constraints the user has flagged (travel, deadlines, busy days). Adjust the plan accordingly.
- Be realistic about capacity. If the user was overloaded last week (overload >= 4), suggest fewer tasks.
- Prioritize by due date and priority number (1 = highest).
- Output your final plan as a clear, readable summary with:
  1. Top priorities for the week (max 5)
  2. Tasks to defer or drop
  3. A brief strategy note
  4. An overload risk assessment (low/medium/high)
- Be concise and direct. No fluff.
"""

MAX_STEPS = 8


def _execute_tool(name: str, input_data: dict) -> str:
    if name == "get_open_tasks":
        tasks = list_tasks(status="open", category=input_data.get("category"))
        due_before = input_data.get("due_before")
        if due_before:
            cutoff = date.fromisoformat(due_before)
            tasks = [t for t in tasks if t.due_date and t.due_date <= cutoff]
        return json.dumps([
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "category": t.category,
                "priority": t.priority,
                "estimated_minutes": t.estimated_minutes,
                "due_date": str(t.due_date) if t.due_date else None,
                "status": t.status,
            }
            for t in tasks
        ])

    elif name == "get_recent_plans":
        limit = input_data.get("limit", 3)
        plans = get_recent_plans(limit=limit)
        return json.dumps(plans)

    elif name == "get_annotations":
        sd = date.fromisoformat(input_data["start_date"])
        ed = date.fromisoformat(input_data["end_date"])
        annotations = list_annotations(from_date=sd, to_date=ed)
        return json.dumps([
            {
                "id": a.id,
                "label": a.label,
                "description": a.description,
                "start_date": str(a.start_date),
                "end_date": str(a.end_date),
            }
            for a in annotations
        ])

    elif name == "get_week_context":
        ws = date.fromisoformat(input_data["week_start"])
        we = ws + timedelta(days=6)
        return json.dumps({
            "week_start": str(ws),
            "week_end": str(we),
            "days": 7,
            "today": str(date.today()),
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


def run_planning_agent(week_start: date) -> dict:
    """Run the agentic planning loop. Returns {"plan_text": str, "trace": list}."""
    client = anthropic.Anthropic()
    model = os.environ.get("PDE_MODEL", "claude-haiku-4-5-20251001")

    messages = [
        {
            "role": "user",
            "content": f"Plan my week starting {week_start.isoformat()}. "
                       f"Use your tools to gather context first, then give me a plan.",
        }
    ]

    trace = []

    for step in range(MAX_STEPS):
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        trace.append({
            "step": step,
            "role": "assistant",
            "stop_reason": response.stop_reason,
            "content": [_serialize_block(b) for b in response.content],
        })

        if response.stop_reason == "end_turn":
            # Agent is done — extract final text
            plan_text = "".join(
                b.text for b in response.content if b.type == "text"
            )
            return {"plan_text": plan_text, "trace": trace}

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
                trace.append({
                    "step": step,
                    "role": "tool",
                    "tool_name": block.name,
                    "input": block.input,
                    "output_preview": result[:500],
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Agent loop exhausted — too many steps without a final answer.")


def _serialize_block(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    elif block.type == "tool_use":
        return {"type": "tool_use", "name": block.name, "input": block.input}
    return {"type": block.type}
