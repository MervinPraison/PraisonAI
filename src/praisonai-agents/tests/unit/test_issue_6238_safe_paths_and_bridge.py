"""Regression tests for Issue #6238.

* Caller-supplied names must never escape the storage directory.
* Sync entry points must work from inside a running event loop.
"""

import asyncio
import os

from praisonaiagents.planning.storage import PlanStorage
from praisonaiagents.planning.todo import TodoList
from praisonaiagents.utils.atomic_io import safe_join


def test_safe_join_keeps_legacy_names_and_confines_others(tmp_path):
    base = str(tmp_path)
    assert safe_join(base, "current", ".json") == os.path.join(base, "current.json")
    for name in ("../../x", "/etc/passwd", "..", "", "a/b", "a\\b", ".hidden"):
        path = safe_join(base, name, ".json")
        assert os.path.dirname(path) == base, name
    # Distinct inputs never collide on one file.
    assert safe_join(base, "a/b") != safe_join(base, "a_b")


def test_plan_storage_todo_name_cannot_traverse(tmp_path):
    storage = PlanStorage(base_path=str(tmp_path / "store"))
    path = storage.save_todo(TodoList(), name="../../escaped")
    assert os.path.dirname(path) == storage.todos_dir
    assert not (tmp_path / "escaped.json").exists()
    assert storage.load_todo("../../escaped") is not None
    assert storage.delete_todo("../../escaped") is True


def test_generate_title_works_inside_running_loop(monkeypatch):
    from praisonaiagents.session import title

    async def fake(*args, **kwargs):
        return "LLM Title"

    monkeypatch.setattr(title, "generate_title_async", fake)

    async def main():
        return title.generate_title("hello", "world")

    assert asyncio.run(main()) == "LLM Title"


def test_listed_todo_names_round_trip(tmp_path):
    storage = PlanStorage(base_path=str(tmp_path / "store"))
    storage.save_todo(TodoList(), name="my tasks")
    (listed,) = storage.list_todos()
    assert storage.load_todo(listed) is not None
    assert storage.load_todo("my tasks") is not None
    assert storage.delete_todo(listed) is True
    assert storage.list_todos() == []


def test_legacy_todo_file_still_found(tmp_path):
    storage = PlanStorage(base_path=str(tmp_path / "store"))
    legacy = os.path.join(storage.todos_dir, "my tasks.json")
    with open(legacy, "w", encoding="utf-8") as f:
        f.write(TodoList().to_json())
    assert storage.load_todo("my tasks") is not None
    assert storage.save_todo(TodoList(), name="my tasks") == legacy
    assert storage.list_todos() == ["my tasks"]
    assert storage.delete_todo("my tasks") is True


def test_custom_plan_filename_keeps_md_suffix(tmp_path):
    from praisonaiagents.planning.plan import Plan

    storage = PlanStorage(base_path=str(tmp_path / "store"))
    plan = Plan(name="demo")
    path = storage.save_plan(plan, filename="my plan.md")
    assert path.endswith(".md") and os.path.dirname(path) == storage.plans_dir
    assert len(storage.list_plans()) == 1
