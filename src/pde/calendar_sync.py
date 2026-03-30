"""
Apple Calendar integration via AppleScript (osascript).

All functions here are pure I/O — no PDE DB imports. They receive plain Python
data (dates, strings) and produce side effects in Calendar.app.

Key design decisions:
- Locale-safe date construction: numeric property assignments instead of string parsing
- Deterministic UIDs: "pde-annotation-7@pde" — stable across re-runs without DB lookup
- uid set post-creation for macOS version compatibility (some versions reject it in make new event)
- All-day events: Calendar.app uses exclusive end dates, so callers must pass end_date + 1 day
"""

import subprocess
from datetime import date


class CalendarSyncError(Exception):
    pass


def make_uid(record_type: str, record_id: int) -> str:
    """Return a stable, deterministic UID for a PDE record.

    Examples:
        make_uid("annotation", 7)  -> "pde-annotation-7@pde"
        make_uid("task", 3)        -> "pde-task-3@pde"
    """
    return f"pde-{record_type}-{record_id}@pde"


def _build_date_script(var_name: str, d: date) -> str:
    """Return locale-safe AppleScript lines that assign a date to a variable.

    Uses numeric property assignment instead of string parsing, so it works
    regardless of the system locale.
    """
    return (
        f"set {var_name} to current date\n"
        f"set year of {var_name} to {d.year}\n"
        f"set month of {var_name} to {d.month}\n"
        f"set day of {var_name} to {d.day}\n"
        f"set time of {var_name} to 0\n"
    )


def run_applescript(script: str) -> str:
    """Execute an AppleScript via osascript. Returns stdout. Raises CalendarSyncError on failure."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CalendarSyncError(result.stderr.strip() or "osascript failed with no error message")
    return result.stdout.strip()


def ensure_calendar_exists(calendar_name: str) -> None:
    """Create the named calendar in Calendar.app if it doesn't already exist."""
    script = f"""
tell application "Calendar"
    if not (exists calendar "{calendar_name}") then
        make new calendar with properties {{name:"{calendar_name}"}}
    end if
end tell
"""
    run_applescript(script)


def create_all_day_event(
    uid: str,
    title: str,
    start_date: date,
    end_date: date,
    notes: str | None,
    calendar_name: str,
) -> None:
    """Create an all-day event in the named calendar.

    end_date should already be end_date + timedelta(days=1) — Calendar.app uses
    exclusive end dates for all-day events. The caller is responsible for this offset.

    The UID is set post-creation for macOS version compatibility.
    """
    date_lines = _build_date_script("startDate", start_date)
    date_lines += _build_date_script("endDate", end_date)

    notes_value = notes.replace('"', '\\"') if notes else ""
    notes_line = f'set description of newEvent to "{notes_value}"\n' if notes else ""

    safe_title = title.replace('"', '\\"')
    safe_uid = uid.replace('"', '\\"')
    safe_calendar = calendar_name.replace('"', '\\"')

    script = f"""
tell application "Calendar"
    tell calendar "{safe_calendar}"
        {date_lines}
        set newEvent to make new event with properties ¬
            {{summary:"{safe_title}", start date:startDate, end date:endDate, allday event:true}}
        {notes_line}set uid of newEvent to "{safe_uid}"
    end tell
end tell
"""
    run_applescript(script)
