"""Regression test for issue #3307 Gap 1.

`Process.aworkflow()` must pre-expand a loop-type start task into one subtask
per input-file row, mirroring the sync `Process.workflow()` behaviour. Before
the fix, the async engine skipped this step (only a TODO comment) and ran the
loop task once as an ordinary task.
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Task
from praisonaiagents.process.process import Process


def _make_loop_process(tmp_path):
    csv_path = os.path.join(tmp_path, "rows.csv")
    with open(csv_path, "w") as fh:
        fh.write("alpha\nbeta\ngamma\n")

    loop_task = Task(
        name="loop_start",
        description="process each row",
        task_type="loop",
        input_file=csv_path,
        is_start=True,
    )
    tasks = {"loop_start": loop_task}
    return Process(tasks=tasks, agents=[]), loop_task


def test_aworkflow_expands_loop_start_task(tmp_path):
    process, loop_task = _make_loop_process(str(tmp_path))

    async def drive():
        gen = process.aworkflow()
        # Pull the first yielded task id; the pre-expansion runs before the
        # first yield, so we only need one step to observe the effect.
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()

    asyncio.run(drive())

    subtasks = [t for t in process.tasks.values()
                if t.name.startswith("loop_start_")]
    # One subtask per CSV row (3 rows) must have been created.
    assert len(subtasks) == 3
    # Parent loop task is marked completed once expanded.
    assert loop_task.status == "completed"


def test_sync_and_async_loop_expansion_match(tmp_path):
    async_process, _ = _make_loop_process(str(tmp_path))

    async def drive():
        gen = async_process.aworkflow()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()

    asyncio.run(drive())
    async_subtasks = {t.name for t in async_process.tasks.values()
                      if t.name.startswith("loop_start_")}

    sync_process, _ = _make_loop_process(str(tmp_path))
    gen = sync_process.workflow()
    try:
        next(gen)
    except StopIteration:
        pass
    gen.close()
    sync_subtasks = {t.name for t in sync_process.tasks.values()
                     if t.name.startswith("loop_start_")}

    assert async_subtasks == sync_subtasks
    assert len(async_subtasks) == 3


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
