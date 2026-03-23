import json
from datetime import date, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from pde.db import init_db
from pde.services import (
    add_task,
    list_tasks,
    complete_task,
    save_plan,
    get_recent_plans,
    log_feedback,
    add_annotation,
    list_annotations,
    delete_annotation,
)
from pde.agent import run_planning_agent

app = typer.Typer(help="PDE — Personal weekly planner with agentic AI")
console = Console()


def _ensure_db():
    init_db()


# ── Task commands ──────────────────────────────────────────

task_app = typer.Typer(help="Manage tasks")
app.add_typer(task_app, name="task")


@task_app.command("add")
def task_add(
    title: str = typer.Argument(..., help="Task title"),
    priority: int = typer.Option(3, "--priority", "-p", min=1, max=5, help="1=highest, 5=lowest"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="Due date (YYYY-MM-DD)"),
    minutes: Optional[int] = typer.Option(None, "--minutes", "-m", help="Estimated minutes"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Category"),
    description: Optional[str] = typer.Option(None, "--desc", help="Description"),
):
    """Add a new task."""
    _ensure_db()
    due_date = date.fromisoformat(due) if due else None
    task = add_task(
        title=title,
        description=description,
        category=category,
        priority=priority,
        estimated_minutes=minutes,
        due_date=due_date,
    )
    console.print(f"[green]Added task #{task.id}:[/green] {task.title}")


@task_app.command("list")
def task_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
):
    """List tasks."""
    _ensure_db()
    tasks = list_tasks(status=status, category=category)
    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style="dim", width=4)
    table.add_column("P", width=2)
    table.add_column("Title")
    table.add_column("Category", style="cyan")
    table.add_column("Due", style="yellow")
    table.add_column("Est", width=5)
    table.add_column("Status")

    for t in tasks:
        status_style = "green" if t.status == "done" else "white"
        table.add_row(
            str(t.id),
            str(t.priority),
            t.title,
            t.category or "",
            str(t.due_date) if t.due_date else "",
            f"{t.estimated_minutes}m" if t.estimated_minutes else "",
            f"[{status_style}]{t.status}[/{status_style}]",
        )
    console.print(table)


@task_app.command("done")
def task_done(task_id: int = typer.Argument(..., help="Task ID to mark as done")):
    """Mark a task as done."""
    _ensure_db()
    try:
        task = complete_task(task_id)
        console.print(f"[green]Completed:[/green] {task.title}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── Annotation commands ────────────────────────────────────

annotation_app = typer.Typer(help="Manage annotations (week constraints, events, notes)")
app.add_typer(annotation_app, name="annotation")


@annotation_app.command("add")
def annotation_add(
    label: str = typer.Argument(..., help="Annotation label (e.g. 'traveling', 'deadline')"),
    start: str = typer.Option(..., "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD). Defaults to start date."),
    description: Optional[str] = typer.Option(None, "--desc", help="Optional description"),
):
    """Add an annotation to a date range."""
    _ensure_db()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else start_date
    ann = add_annotation(
        start_date=start_date,
        end_date=end_date,
        label=label,
        description=description,
    )
    console.print(f"[green]Added annotation #{ann.id}:[/green] {ann.label} ({ann.start_date} → {ann.end_date})")


@annotation_app.command("list")
def annotation_list(
    week: Optional[str] = typer.Option(None, "--week", "-w", help="Show annotations overlapping this week (YYYY-MM-DD Monday)"),
):
    """List annotations."""
    _ensure_db()
    if week:
        from_date = date.fromisoformat(week)
        to_date = from_date + timedelta(days=6)
    else:
        from_date = None
        to_date = None

    annotations = list_annotations(from_date=from_date, to_date=to_date)
    if not annotations:
        console.print("[dim]No annotations found.[/dim]")
        return

    table = Table(title="Annotations")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Label")
    table.add_column("Start", style="yellow")
    table.add_column("End", style="yellow")
    table.add_column("Description", style="cyan")

    for a in annotations:
        table.add_row(
            str(a.id),
            a.label,
            str(a.start_date),
            str(a.end_date),
            a.description or "",
        )
    console.print(table)


@annotation_app.command("remove")
def annotation_remove(
    annotation_id: int = typer.Argument(..., help="Annotation ID to remove"),
):
    """Remove an annotation."""
    _ensure_db()
    try:
        delete_annotation(annotation_id)
        console.print(f"[green]Removed annotation #{annotation_id}.[/green]")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── Plan command ───────────────────────────────────────────


@app.command("plan")
def plan(
    date_str: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Monday to plan for (YYYY-MM-DD). Defaults to next Monday.",
    ),
):
    """Generate a weekly plan using the AI agent."""
    _ensure_db()

    if date_str:
        week_start = date.fromisoformat(date_str)
    else:
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday)

    console.print(f"[bold]Planning week of {week_start}...[/bold]\n")

    try:
        result = run_planning_agent(week_start)
    except Exception as e:
        console.print(f"[red]Agent error:[/red] {e}")
        raise typer.Exit(1)

    plan_obj = save_plan(
        week_start=week_start,
        plan_text=result["plan_text"],
        interaction_trace=json.dumps(result["trace"]),
    )

    console.print(Panel(
        Markdown(result["plan_text"]),
        title=f"Week Plan #{plan_obj.id} ({week_start} → {plan_obj.week_end})",
        border_style="blue",
    ))
    console.print(f"\n[dim]Plan saved as #{plan_obj.id}. Use 'pde feedback {plan_obj.id}' later to log how it went.[/dim]")


# ── Feedback command ───────────────────────────────────────


@app.command("feedback")
def feedback(
    plan_id: int = typer.Argument(..., help="Plan ID to give feedback on"),
):
    """Log feedback on how a plan went."""
    _ensure_db()

    console.print(f"[bold]Feedback for plan #{plan_id}[/bold]\n")
    console.print("[dim]Rate 1-5 for each (1=lowest, 5=highest):[/dim]")

    adherence = typer.prompt("Adherence (how closely did you follow the plan?)", type=int)
    satisfaction = typer.prompt("Satisfaction (how good was the plan?)", type=int)
    overload = typer.prompt("Overload (how overwhelmed were you?)", type=int)
    notes = typer.prompt("Notes (optional)", default="", show_default=False)

    for val, name in [(adherence, "adherence"), (satisfaction, "satisfaction"), (overload, "overload")]:
        if not 1 <= val <= 5:
            console.print(f"[red]{name} must be 1-5[/red]")
            raise typer.Exit(1)

    try:
        fb = log_feedback(
            plan_id=plan_id,
            adherence=adherence,
            satisfaction=satisfaction,
            overload=overload,
            notes=notes or None,
        )
        console.print(f"\n[green]Feedback logged.[/green] (adherence={fb.adherence}, satisfaction={fb.satisfaction}, overload={fb.overload})")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── History command ────────────────────────────────────────


@app.command("history")
def history(
    limit: int = typer.Option(5, "--limit", "-n", help="Number of recent plans to show"),
):
    """Show past plans and their feedback."""
    _ensure_db()

    plans = get_recent_plans(limit=limit)
    if not plans:
        console.print("[dim]No plans yet. Run 'pde plan' to create one.[/dim]")
        return

    for p in plans:
        fb = p["feedback"]
        fb_str = (
            f"adherence={fb['adherence']} satisfaction={fb['satisfaction']} overload={fb['overload']}"
            if fb else "[dim]no feedback yet[/dim]"
        )

        console.print(Panel(
            f"{p['plan_text']}\n\n[bold]Feedback:[/bold] {fb_str}"
            + (f"\n[italic]{fb['notes']}[/italic]" if fb and fb.get("notes") else ""),
            title=f"Plan #{p['id']} — {p['week_start']} → {p['week_end']}",
            border_style="blue",
        ))


if __name__ == "__main__":
    app()
