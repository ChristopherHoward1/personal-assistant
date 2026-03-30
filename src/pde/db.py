import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import inspect, text
from sqlmodel import Field, SQLModel, create_engine, Session

# Store DB in ~/.pde/ so data is decoupled from the project directory
_pde_dir = Path(os.environ.get("PDE_DATA_DIR", Path.home() / ".pde"))
_pde_dir.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{_pde_dir / 'pde.db'}"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    priority: int = Field(default=3)  # 1 = highest, 5 = lowest
    estimated_minutes: Optional[int] = None
    due_date: Optional[date] = None
    status: str = Field(default="open")  # open, done, deferred
    cal_uid: Optional[str] = None  # set after syncing to Apple Calendar
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


class Plan(SQLModel, table=True):
    __tablename__ = "plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    week_start: date
    week_end: date
    interaction_trace: Optional[str] = None  # JSON: full agent tool-call trace
    plan_json: Optional[str] = None  # JSON: the final structured plan
    plan_text: Optional[str] = None  # human-readable plan
    model_name: str = Field(default="claude-haiku-4-5-20251001")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="plans.id")
    adherence: int = Field(ge=1, le=5)  # 1 = didn't follow at all, 5 = followed exactly
    satisfaction: int = Field(ge=1, le=5)
    overload: int = Field(ge=1, le=5)  # 1 = underloaded, 5 = overwhelmed
    notes: Optional[str] = None
    task_results_json: Optional[str] = None  # JSON: [{"task_id": 1, "title": "...", "completed": true}, ...]
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


class Annotation(SQLModel, table=True):
    __tablename__ = "annotations"

    id: Optional[int] = Field(default=None, primary_key=True)
    start_date: date
    end_date: date
    label: str
    description: Optional[str] = None
    cal_uid: Optional[str] = None  # set after syncing to Apple Calendar
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


engine = create_engine(DATABASE_URL)


def _migrate_add_cal_uid():
    """Add cal_uid column to tasks and annotations if not present. Safe to call on every startup."""
    with engine.connect() as conn:
        inspector = inspect(engine)
        for table_name in ("tasks", "annotations"):
            columns = [c["name"] for c in inspector.get_columns(table_name)]
            if "cal_uid" not in columns:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN cal_uid VARCHAR"))
        conn.commit()


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate_add_cal_uid()


def get_session():
    return Session(engine)
