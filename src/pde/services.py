import json
from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import select

from pde.db import Task, Plan, Feedback, Annotation, get_session


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


# ── Week stats ─────────────────────────────────────────────


def get_week_stats(week_start: date) -> dict:
    """Compute workload stats for a given week. Used by the agent's get_week_context tool."""
    week_end = week_start + timedelta(days=6)
    open_tasks = list_tasks(status="open")

    due_this_week = [
        t for t in open_tasks
        if t.due_date and week_start <= t.due_date <= week_end
    ]
    high_priority = [t for t in open_tasks if t.priority <= 2]

    total_minutes = sum(t.estimated_minutes or 0 for t in open_tasks)
    week_minutes = sum(t.estimated_minutes or 0 for t in due_this_week)

    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "today": str(date.today()),
        "open_task_count": len(open_tasks),
        "due_this_week_count": len(due_this_week),
        "high_priority_count": len(high_priority),
        "total_estimated_minutes": total_minutes,
        "week_estimated_minutes": week_minutes,
    }


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


def get_plan(plan_id: int) -> Optional[Plan]:
    with get_session() as session:
        return session.get(Plan, plan_id)


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
            fb_data = None
            if fb:
                fb_data = {
                    "adherence": fb.adherence,
                    "satisfaction": fb.satisfaction,
                    "overload": fb.overload,
                    "notes": fb.notes,
                }
                if fb.task_results_json:
                    fb_data["task_results"] = json.loads(fb.task_results_json)
            results.append({
                "id": p.id,
                "week_start": str(p.week_start),
                "week_end": str(p.week_end),
                "plan_text": p.plan_text,
                "feedback": fb_data,
            })
        return results


# ── Feedback ───────────────────────────────────────────────


# ── Annotation CRUD ────────────────────────────────────────


def add_annotation(
    start_date: date,
    end_date: date,
    label: str,
    description: Optional[str] = None,
) -> Annotation:
    annotation = Annotation(
        start_date=start_date,
        end_date=end_date,
        label=label,
        description=description,
    )
    with get_session() as session:
        session.add(annotation)
        session.commit()
        session.refresh(annotation)
        return annotation


def list_annotations(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[Annotation]:
    """List annotations, optionally filtered to those overlapping a date range."""
    with get_session() as session:
        stmt = select(Annotation)
        if from_date and to_date:
            # Overlap: annotation.start <= range.end AND annotation.end >= range.start
            stmt = stmt.where(
                Annotation.start_date <= to_date,
                Annotation.end_date >= from_date,
            )
        stmt = stmt.order_by(Annotation.start_date)
        return list(session.exec(stmt).all())


def delete_annotation(annotation_id: int) -> None:
    with get_session() as session:
        annotation = session.get(Annotation, annotation_id)
        if not annotation:
            raise ValueError(f"Annotation {annotation_id} not found")
        session.delete(annotation)
        session.commit()


# ── Feedback ───────────────────────────────────────────────


# ── Calendar sync helpers ──────────────────────────────────


def get_unsynced_annotations() -> list[Annotation]:
    """Return annotations that have not yet been synced to Apple Calendar."""
    with get_session() as session:
        stmt = select(Annotation).where(Annotation.cal_uid == None).order_by(Annotation.start_date)
        return list(session.exec(stmt).all())


def get_unsynced_tasks_with_due_date() -> list[Task]:
    """Return open tasks with a due_date that have not yet been synced to Apple Calendar."""
    with get_session() as session:
        stmt = (
            select(Task)
            .where(Task.status == "open")
            .where(Task.due_date != None)
            .where(Task.cal_uid == None)
            .order_by(Task.due_date)
        )
        return list(session.exec(stmt).all())


def mark_annotation_synced(annotation_id: int, cal_uid: str) -> None:
    with get_session() as session:
        annotation = session.get(Annotation, annotation_id)
        if not annotation:
            raise ValueError(f"Annotation {annotation_id} not found")
        annotation.cal_uid = cal_uid
        session.add(annotation)
        session.commit()


def mark_task_synced(task_id: int, cal_uid: str) -> None:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.cal_uid = cal_uid
        session.add(task)
        session.commit()


def log_feedback(
    plan_id: int,
    adherence: int,
    satisfaction: int,
    overload: int,
    notes: Optional[str] = None,
    task_results: Optional[list[dict]] = None,
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
            task_results_json=json.dumps(task_results) if task_results else None,
        )
        session.add(fb)
        session.commit()
        session.refresh(fb)
        return fb
