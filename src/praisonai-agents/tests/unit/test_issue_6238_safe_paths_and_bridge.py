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


def test_encoded_looking_names_do_not_share_a_file(tmp_path):
    storage = PlanStorage(base_path=str(tmp_path / "store"))
    names = ["a/b", "a_b~c14cddc033f6", "a%2Fb", "a b", "a%20b", "~x", ".."]
    paths = {storage.save_todo(TodoList(name=n), name=n) for n in names}
    assert len(paths) == len(names)
    assert all(os.path.dirname(p) == storage.todos_dir for p in paths)
    assert sorted(storage.list_todos()) == sorted(names)
    for n in names:
        assert storage.load_todo(n).name == n
    assert storage.delete_todo("a/b") is True
    assert storage.load_todo("a%2Fb") is not None


def test_long_unicode_names_are_bounded_and_round_trip(tmp_path):
    storage = PlanStorage(base_path=str(tmp_path / "store"))
    long_a, long_b = "我的任务" * 40, "我的任务" * 40 + "x"
    pa = storage.save_todo(TodoList(name=long_a), name=long_a)
    pb = storage.save_todo(TodoList(name=long_b), name=long_b)
    assert pa != pb
    for p in (pa, pb):
        assert os.path.dirname(p) == storage.todos_dir
        assert len(os.path.basename(p).encode("utf-8")) <= 200
    # Short non-ASCII names keep their plain (pre-#6238) filename.
    assert storage.save_todo(TodoList(), name="我的任务").endswith("我的任务.json")
    for listed in storage.list_todos():
        assert storage.load_todo(listed) is not None
        assert storage.delete_todo(listed) is True
    assert storage.list_todos() == []
    assert storage.load_todo(long_a) is None
