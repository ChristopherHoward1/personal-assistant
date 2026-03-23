from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine, Session

DATABASE_URL = "sqlite:///pde.db"


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


engine = create_engine(DATABASE_URL)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
