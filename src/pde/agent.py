import json
import os
from datetime import date, timedelta

import anthropic

from pde.services import list_tasks, get_recent_plans, list_annotations, get_week_stats

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
        "description": "Retrieve recent weekly plans and their feedback scores. Use this to see what worked and what didn't in past weeks.",
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
        "description": "Get a workload snapshot for the planning week: task counts, estimated hours, due dates, high-priority count. Call this first to get a quick overview.",
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
    {
        "name": "submit_plan",
        "description": "Submit the final weekly plan. You MUST call this exactly once to deliver your plan. Do not just end with text — always call this tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "priority_tasks": {
                    "type": "array",
                    "description": "Tasks to prioritize this week, in order of importance (max 7).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["task_id", "title", "reason"],
                    },
                },
                "defer_tasks": {
                    "type": "array",
                    "description": "Tasks to explicitly defer or drop this week, with reasons.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["task_id", "title", "reason"],
                    },
                },
                "strategy": {
                    "type": "string",
                    "description": "Brief strategy note for the week (1-3 sentences).",
                },
                "overload_risk": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Overall overload risk assessment.",
                },
                "plan_summary": {
                    "type": "string",
                    "description": "Human-readable markdown summary of the full plan.",
                },
            },
            "required": ["priority_tasks", "defer_tasks", "strategy", "overload_risk", "plan_summary"],
        },
    },
]

SYSTEM_PROMPT = """\
You are a personal weekly planner. Your job is to help the user plan their upcoming week.

You have tools to retrieve open tasks, past plans, annotations, and week context.

Workflow:
1. Call get_week_context to get a workload snapshot.
2. Call get_annotations to check for constraints (travel, deadlines, busy days).
3. Call get_open_tasks to see the full task list.
4. Optionally call get_recent_plans to review past performance and feedback.
5. Reason about priorities, capacity, and constraints.
6. Call submit_plan with your structured plan. You MUST call submit_plan to finish.

Rules:
- Be realistic about capacity. A normal week fits 15-20 hours of focused task work.
- If past feedback shows overload (overload >= 4), suggest fewer tasks.
- Prioritize by due date and priority number (1 = highest).
- Always check annotations — adjust the plan for travel, deadlines, and constraints.
- When deferring tasks, give a specific reason.
- Be concise and direct. No fluff.
"""

MAX_STEPS = 10


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
        return json.dumps(get_week_stats(ws))

    elif name == "submit_plan":
        # Not executed — handled in the agent loop
        return json.dumps({"status": "accepted"})

    return json.dumps({"error": f"Unknown tool: {name}"})


def run_planning_agent(week_start: date, note: str | None = None) -> dict:
    """Run the agentic planning loop.

    Returns {
        "plan_text": str,
        "plan_json": dict,  # structured plan from submit_plan
        "trace": list,
    }
    """
    client = anthropic.Anthropic()
    model = os.environ.get("PDE_MODEL", "claude-haiku-4-5-20251001")

    user_msg = f"Plan my week starting {week_start.isoformat()}."
    if note:
        user_msg += f"\n\nContext from user: {note}"
    user_msg += "\n\nUse your tools to gather context, then call submit_plan with your plan."

    messages = [{"role": "user", "content": user_msg}]
    trace = []

    for step in range(MAX_STEPS):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
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

        # Check for submit_plan in tool calls
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_plan":
                plan_data = block.input
                trace.append({
                    "step": step,
                    "role": "tool",
                    "tool_name": "submit_plan",
                    "input": plan_data,
                })
                return {
                    "plan_text": plan_data.get("plan_summary", ""),
                    "plan_json": plan_data,
                    "trace": trace,
                }

        if response.stop_reason == "end_turn":
            # Agent ended without calling submit_plan — extract text as fallback
            plan_text = "".join(
                b.text for b in response.content if b.type == "text"
            )
            return {"plan_text": plan_text, "plan_json": None, "trace": trace}

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
