from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import select

from pde.db import Task, Plan, Feedback, get_session


# ── Task CRUD ──────────────────────────────────────────────


def add_task(
    title: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    priority: int = 3,
    estimated_minutes: Optional[int] = None,
    due_date: Optional[date] = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        category=category,
        priority=priority,
        estimated_minutes=estimated_minutes,
        due_date=due_date,
    )
    with get_session() as session:
        session.add(task)
        session.commit()
        session.refresh(task)
        return task


def list_tasks(
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> list[Task]:
    with get_session() as session:
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        if category:
            stmt = stmt.where(Task.category == category)
        stmt = stmt.order_by(Task.priority, Task.due_date)
        return list(session.exec(stmt).all())


def complete_task(task_id: int) -> Task:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = "done"
        task.updated_at = datetime.now(tz=None)
        session.add(task)
        session.commit()
        session.refresh(task)
        return task


# ── Plan helpers ───────────────────────────────────────────


def save_plan(
    week_start: date,
    plan_text: str,
    plan_json: Optional[str] = None,
    interaction_trace: Optional[str] = None,
    model_name: str = "claude-haiku-4-5-20251001",
) -> Plan:
    week_end = week_start + timedelta(days=6)
    plan = Plan(
        week_start=week_start,
        week_end=week_end,
        plan_text=plan_text,
        plan_json=plan_json,
        interaction_trace=interaction_trace,
        model_name=model_name,
    )
    with get_session() as session:
        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan


def get_recent_plans(limit: int = 3) -> list[dict]:
    """Return recent plans with their feedback joined."""
    with get_session() as session:
        plans = list(
            session.exec(
                select(Plan).order_by(Plan.created_at.desc()).limit(limit)
            ).all()
        )
        results = []
        for p in plans:
            fb = session.exec(
                select(Feedback).where(Feedback.plan_id == p.id)
            ).first()
            results.append({
                "id": p.id,
                "week_start": str(p.week_start),
                "week_end": str(p.week_end),
                "plan_text": p.plan_text,
                "feedback": {
                    "adherence": fb.adherence,
                    "satisfaction": fb.satisfaction,
                    "overload": fb.overload,
                    "notes": fb.notes,
                } if fb else None,
            })
        return results


# ── Feedback ───────────────────────────────────────────────


def log_feedback(
    plan_id: int,
    adherence: int,
    satisfaction: int,
    overload: int,
    notes: Optional[str] = None,
) -> Feedback:
    with get_session() as session:
        plan = session.get(Plan, plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        fb = Feedback(
            plan_id=plan_id,
            adherence=adherence,
            satisfaction=satisfaction,
            overload=overload,
            notes=notes,
        )
        session.add(fb)
        session.commit()
        session.refresh(fb)
        return fb
