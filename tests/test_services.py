import os
import pytest
from datetime import date

# Use in-memory DB for tests
os.environ["PDE_TEST"] = "1"

from pde.db import SQLModel, Task, Plan, Feedback, Annotation, init_db, engine, get_session
from pde.services import (
    add_task,
    list_tasks,
    complete_task,
    save_plan,
    get_plan,
    get_recent_plans,
    get_week_stats,
    log_feedback,
    add_annotation,
    list_annotations,
    delete_annotation,
)


@pytest.fixture(autouse=True)
def fresh_db():
    """Create fresh tables for each test."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


class TestTaskCRUD:
    def test_add_task(self):
        task = add_task(title="Write tests", priority=1)
        assert task.id is not None
        assert task.title == "Write tests"
        assert task.priority == 1
        assert task.status == "open"

    def test_add_task_with_all_fields(self):
        task = add_task(
            title="Deploy app",
            description="Deploy to prod",
            category="work",
            priority=2,
            estimated_minutes=30,
            due_date=date(2026, 3, 25),
        )
        assert task.category == "work"
        assert task.estimated_minutes == 30
        assert task.due_date == date(2026, 3, 25)

    def test_list_tasks_empty(self):
        assert list_tasks() == []

    def test_list_tasks_filters_by_status(self):
        add_task(title="Open task")
        t2 = add_task(title="Done task")
        complete_task(t2.id)

        open_tasks = list_tasks(status="open")
        assert len(open_tasks) == 1
        assert open_tasks[0].title == "Open task"

    def test_list_tasks_filters_by_category(self):
        add_task(title="Work task", category="work")
        add_task(title="Personal task", category="personal")

        work = list_tasks(category="work")
        assert len(work) == 1
        assert work[0].title == "Work task"

    def test_list_tasks_ordered_by_priority(self):
        add_task(title="Low priority", priority=5)
        add_task(title="High priority", priority=1)

        tasks = list_tasks()
        assert tasks[0].title == "High priority"
        assert tasks[1].title == "Low priority"

    def test_complete_task(self):
        task = add_task(title="To complete")
        completed = complete_task(task.id)
        assert completed.status == "done"

    def test_complete_nonexistent_task(self):
        with pytest.raises(ValueError, match="not found"):
            complete_task(9999)


class TestPlans:
    def test_save_plan(self):
        plan = save_plan(
            week_start=date(2026, 3, 23),
            plan_text="Focus on testing this week.",
        )
        assert plan.id is not None
        assert plan.week_start == date(2026, 3, 23)
        assert plan.week_end == date(2026, 3, 29)

    def test_get_recent_plans_empty(self):
        assert get_recent_plans() == []

    def test_get_recent_plans_with_feedback(self):
        plan = save_plan(week_start=date(2026, 3, 23), plan_text="Test plan")
        log_feedback(plan_id=plan.id, adherence=4, satisfaction=5, overload=2, notes="Good week")

        plans = get_recent_plans(limit=1)
        assert len(plans) == 1
        assert plans[0]["feedback"]["adherence"] == 4
        assert plans[0]["feedback"]["notes"] == "Good week"


class TestFeedback:
    def test_log_feedback(self):
        plan = save_plan(week_start=date(2026, 3, 23), plan_text="Test")
        fb = log_feedback(plan_id=plan.id, adherence=3, satisfaction=4, overload=2)
        assert fb.id is not None
        assert fb.adherence == 3

    def test_log_feedback_with_task_results(self):
        plan = save_plan(week_start=date(2026, 3, 23), plan_text="Test")
        task_results = [
            {"task_id": 1, "title": "Write tests", "completed": True},
            {"task_id": 2, "title": "Deploy", "completed": False},
        ]
        fb = log_feedback(
            plan_id=plan.id, adherence=4, satisfaction=3, overload=2,
            task_results=task_results,
        )
        assert fb.task_results_json is not None
        import json
        results = json.loads(fb.task_results_json)
        assert len(results) == 2
        assert results[0]["completed"] is True
        assert results[1]["completed"] is False

    def test_feedback_nonexistent_plan(self):
        with pytest.raises(ValueError, match="not found"):
            log_feedback(plan_id=9999, adherence=3, satisfaction=3, overload=3)


class TestWeekStats:
    def test_week_stats_empty(self):
        stats = get_week_stats(date(2026, 3, 23))
        assert stats["open_task_count"] == 0
        assert stats["due_this_week_count"] == 0
        assert stats["total_estimated_minutes"] == 0

    def test_week_stats_with_tasks(self):
        add_task(title="Due this week", priority=1, estimated_minutes=60, due_date=date(2026, 3, 25))
        add_task(title="Due next week", priority=3, estimated_minutes=30, due_date=date(2026, 4, 1))
        add_task(title="High priority no due", priority=2, estimated_minutes=45)

        stats = get_week_stats(date(2026, 3, 23))
        assert stats["open_task_count"] == 3
        assert stats["due_this_week_count"] == 1
        assert stats["high_priority_count"] == 2  # priority 1 and 2
        assert stats["total_estimated_minutes"] == 135
        assert stats["week_estimated_minutes"] == 60

    def test_get_plan(self):
        plan = save_plan(week_start=date(2026, 3, 23), plan_text="Test")
        fetched = get_plan(plan.id)
        assert fetched is not None
        assert fetched.plan_text == "Test"

    def test_get_plan_nonexistent(self):
        assert get_plan(9999) is None


class TestAnnotations:
    def test_add_annotation(self):
        ann = add_annotation(
            start_date=date(2026, 3, 23),
            end_date=date(2026, 3, 25),
            label="traveling",
            description="Conference in Austin",
        )
        assert ann.id is not None
        assert ann.label == "traveling"
        assert ann.start_date == date(2026, 3, 23)
        assert ann.end_date == date(2026, 3, 25)

    def test_add_annotation_single_day(self):
        ann = add_annotation(
            start_date=date(2026, 3, 27),
            end_date=date(2026, 3, 27),
            label="deadline",
        )
        assert ann.description is None
        assert ann.start_date == ann.end_date

    def test_list_annotations_by_date_range(self):
        add_annotation(start_date=date(2026, 3, 23), end_date=date(2026, 3, 25), label="traveling")
        add_annotation(start_date=date(2026, 3, 27), end_date=date(2026, 3, 27), label="deadline")
        add_annotation(start_date=date(2026, 4, 1), end_date=date(2026, 4, 3), label="next week thing")

        # Query the week of March 23-29
        results = list_annotations(from_date=date(2026, 3, 23), to_date=date(2026, 3, 29))
        assert len(results) == 2
        assert results[0].label == "traveling"
        assert results[1].label == "deadline"

    def test_list_annotations_no_overlap(self):
        add_annotation(start_date=date(2026, 4, 1), end_date=date(2026, 4, 3), label="future")

        results = list_annotations(from_date=date(2026, 3, 23), to_date=date(2026, 3, 29))
        assert results == []

    def test_list_annotations_partial_overlap(self):
        # Annotation starts before range, ends during range
        add_annotation(start_date=date(2026, 3, 20), end_date=date(2026, 3, 24), label="overlaps start")

        results = list_annotations(from_date=date(2026, 3, 23), to_date=date(2026, 3, 29))
        assert len(results) == 1
        assert results[0].label == "overlaps start"

    def test_list_all_annotations(self):
        add_annotation(start_date=date(2026, 3, 23), end_date=date(2026, 3, 25), label="a")
        add_annotation(start_date=date(2026, 4, 1), end_date=date(2026, 4, 3), label="b")

        results = list_annotations()
        assert len(results) == 2

    def test_delete_annotation(self):
        ann = add_annotation(start_date=date(2026, 3, 23), end_date=date(2026, 3, 25), label="to delete")
        delete_annotation(ann.id)
        assert list_annotations() == []

    def test_delete_nonexistent_annotation(self):
        with pytest.raises(ValueError, match="not found"):
            delete_annotation(9999)
