import json
import os
from datetime import date, timedelta
from typing import Optional

from dotenv import load_dotenv, find_dotenv
import typer

# Load .env by searching upward from cwd (works on all platforms and install methods)
_env_file = find_dotenv(usecwd=True)
if _env_file:
    load_dotenv(_env_file, override=True)
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
    get_plan,
    get_recent_plans,
    log_feedback,
    add_annotation,
    list_annotations,
    delete_annotation,
    get_unsynced_annotations,
    get_unsynced_tasks_with_due_date,
    mark_annotation_synced,
    mark_task_synced,
)
from pde.agent import run_planning_agent, run_quick_agent

app = typer.Typer(help="PDE — Personal weekly planner with agentic AI")
console = Console()


def _ensure_db():
    init_db()


def _require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY is not set.")
        console.print(
            "Set it as an environment variable or add it to a .env file in your project directory."
        )
        raise typer.Exit(1)


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


# ── Quick input command ────────────────────────────────────


@app.command("quick")
def quick(
    text: str = typer.Argument(..., help="Natural language input describing tasks, events, or reminders."),
):
    """Quickly add tasks and events using natural language.

    Examples:
        pde quick "therapy Saturday at 2pm, dentist Monday at 10am"
        pde quick "email Alice about the proposal by Friday"
        pde quick "team offsite next Tue-Thu, prep slides by Monday"
    """
    _ensure_db()
    _require_api_key()

    console.print(f"[dim]Parsing:[/dim] {text}\n")

    try:
        result = run_quick_agent(text)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for item in result["created"]:
        if item.get("type") == "task":
            due_str = f" (due {item['due_date']})" if item.get("due_date") else ""
            console.print(f"  [green]+ Task #{item['id']}:[/green] {item['title']}{due_str}")
        elif item.get("type") == "annotation":
            console.print(f"  [blue]+ Event #{item['id']}:[/blue] {item['label']} ({item['start_date']})")

    if not result["created"]:
        console.print("[yellow]No items created.[/yellow]")


# ── Plan command ───────────────────────────────────────────


@app.command("plan")
def plan(
    date_str: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Monday to plan for (YYYY-MM-DD). Defaults to this Monday (or next if past Wednesday).",
    ),
    note: Optional[str] = typer.Option(
        None, "--note", "-n",
        help="Context for the planner (e.g. 'light week, focus on deep work').",
    ),
):
    """Generate a weekly plan using the AI agent."""
    _ensure_db()

    if date_str:
        week_start = date.fromisoformat(date_str)
    else:
        today = date.today()
        weekday = today.weekday()  # 0=Mon
        if weekday <= 2:
            # Mon-Wed: plan this week (rewind to Monday)
            week_start = today - timedelta(days=weekday)
        else:
            # Thu-Sun: plan next week
            week_start = today + timedelta(days=(7 - weekday))

    _require_api_key()

    console.print(f"[bold]Planning week of {week_start}...[/bold]\n")

    try:
        result = run_planning_agent(week_start, note=note)
    except Exception as e:
        console.print(f"[red]Agent error:[/red] {e}")
        raise typer.Exit(1)

    plan_json_str = json.dumps(result["plan_json"]) if result.get("plan_json") else None

    plan_obj = save_plan(
        week_start=week_start,
        plan_text=result["plan_text"],
        plan_json=plan_json_str,
        interaction_trace=json.dumps(result["trace"]),
    )

    console.print(Panel(
        Markdown(result["plan_text"]),
        title=f"Week Plan #{plan_obj.id} ({week_start} → {plan_obj.week_end})",
        border_style="blue",
    ))

    # Show structured summary if available
    pj = result.get("plan_json")
    if pj:
        risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(pj.get("overload_risk", ""), "white")
        console.print(f"\n  Overload risk: [{risk_color}]{pj.get('overload_risk', '?')}[/{risk_color}]")
        console.print(f"  Priority tasks: {len(pj.get('priority_tasks', []))}  |  Deferred: {len(pj.get('defer_tasks', []))}")

    console.print(f"\n[dim]Plan saved as #{plan_obj.id}. Use 'pde feedback {plan_obj.id}' later to log how it went.[/dim]")


# ── Feedback command ───────────────────────────────────────


@app.command("feedback")
def feedback(
    plan_id: int = typer.Argument(..., help="Plan ID to give feedback on"),
):
    """Log feedback on how a plan went, including task-level results."""
    _ensure_db()

    plan_obj = get_plan(plan_id)
    if not plan_obj:
        console.print(f"[red]Plan #{plan_id} not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Feedback for plan #{plan_id} ({plan_obj.week_start} → {plan_obj.week_end})[/bold]\n")

    # Task-level feedback if we have structured plan data
    task_results = []
    if plan_obj.plan_json:
        plan_data = json.loads(plan_obj.plan_json)
        priority_tasks = plan_data.get("priority_tasks", [])
        if priority_tasks:
            console.print("[bold]Priority tasks — did you complete them?[/bold]")
            for pt in priority_tasks:
                done = typer.confirm(f"  {pt['title']} (#{pt['task_id']})?", default=False)
                task_results.append({
                    "task_id": pt["task_id"],
                    "title": pt["title"],
                    "completed": done,
                })
                # Mark task as done in DB if completed
                if done:
                    try:
                        complete_task(pt["task_id"])
                    except ValueError:
                        pass  # task may already be done or deleted
            console.print()

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
            task_results=task_results or None,
        )
        done_count = sum(1 for t in task_results if t["completed"]) if task_results else 0
        total_count = len(task_results) if task_results else 0
        console.print(f"\n[green]Feedback logged.[/green]")
        console.print(f"  Scores: adherence={fb.adherence} satisfaction={fb.satisfaction} overload={fb.overload}")
        if task_results:
            console.print(f"  Tasks completed: {done_count}/{total_count}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── Calendar commands ──────────────────────────────────────

calendar_app = typer.Typer(help="Sync PDE data to Apple Calendar (macOS only)")
app.add_typer(calendar_app, name="calendar")


@calendar_app.command("sync")
def calendar_sync(
    calendar_name: str = typer.Option("PDE", "--calendar", "-c", help="Apple Calendar name to sync into"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be synced without making changes"),
):
    """Push annotations and task deadlines to Apple Calendar.

    Creates a dedicated 'PDE' calendar (or whichever name you specify) and adds:
    - Annotations as all-day events
    - Tasks with due dates as 'DUE: <title>' all-day events

    Safe to run multiple times — already-synced items are skipped.

    macOS will prompt for Calendar access on the first run.
    """
    import sys
    if sys.platform != "darwin":
        console.print("[red]Calendar sync is macOS only.[/red]")
        raise typer.Exit(1)

    from datetime import timedelta
    from pde.calendar_sync import make_uid, ensure_calendar_exists, create_all_day_event, CalendarSyncError

    _ensure_db()

    unsynced_annotations = get_unsynced_annotations()
    unsynced_tasks = get_unsynced_tasks_with_due_date()

    total = len(unsynced_annotations) + len(unsynced_tasks)
    if total == 0:
        console.print("[dim]Nothing new to sync. All items are up to date.[/dim]")
        return

    if dry_run:
        console.print(f"[bold][DRY RUN] Would sync {total} item(s) to calendar '{calendar_name}':[/bold]\n")
        for a in unsynced_annotations:
            console.print(f"  [blue]Event:[/blue] {a.label}  ({a.start_date} → {a.end_date})")
        for t in unsynced_tasks:
            console.print(f"  [yellow]Deadline:[/yellow] DUE: {t.title}  ({t.due_date})")
        return

    # Ensure the calendar exists before starting (triggers permission prompt if needed)
    try:
        ensure_calendar_exists(calendar_name)
    except CalendarSyncError as e:
        console.print(f"[red]Could not access Calendar.app:[/red] {e}")
        console.print("[dim]Make sure Calendar is installed and macOS has granted access.[/dim]")
        raise typer.Exit(1)

    created = 0
    failed = 0

    for a in unsynced_annotations:
        uid = make_uid("annotation", a.id)
        try:
            create_all_day_event(
                uid=uid,
                title=a.label,
                start_date=a.start_date,
                end_date=a.end_date + timedelta(days=1),  # Calendar uses exclusive end dates
                notes=a.description,
                calendar_name=calendar_name,
            )
            mark_annotation_synced(a.id, uid)
            console.print(f"  [green]Synced event:[/green] {a.label} ({a.start_date} → {a.end_date})")
            created += 1
        except CalendarSyncError as e:
            console.print(f"  [red]Failed:[/red] annotation #{a.id} ({a.label}) — {e}")
            failed += 1

    for t in unsynced_tasks:
        uid = make_uid("task", t.id)
        title = f"DUE: {t.title}"
        try:
            create_all_day_event(
                uid=uid,
                title=title,
                start_date=t.due_date,
                end_date=t.due_date + timedelta(days=1),
                notes=t.description,
                calendar_name=calendar_name,
            )
            mark_task_synced(t.id, uid)
            console.print(f"  [green]Synced deadline:[/green] {title} ({t.due_date})")
            created += 1
        except CalendarSyncError as e:
            console.print(f"  [red]Failed:[/red] task #{t.id} ({t.title}) — {e}")
            failed += 1

    console.print(f"\n[bold]Done.[/bold] {created} synced" + (f", {failed} failed" if failed else "") + f" → calendar '{calendar_name}'")


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
