# Scheduler — runner vs loop

## ScheduleRunner (stateless)

`ScheduleRunner` is **stateless**. Call `get_due_jobs()` whenever you want to check for jobs that should fire. It does not run background threads.

Use when:
- CLI one-shot tick (`praisonai schedule tick`)
- Host integration that polls on its own timer
- Tests

## ScheduleLoop (optional daemon)

`ScheduleLoop` is an **optional background daemon**. You must call `.start()` explicitly; it polls the runner and invokes `on_trigger` callbacks.

Use when:
- Long-running host process (Pattern B/C via `setup_bridges()`)
- Standalone scheduler service

```python
from praisonaiagents.scheduler import FileScheduleStore, ScheduleRunner, ScheduleLoop

store = FileScheduleStore()
runner = ScheduleRunner(store)
loop = ScheduleLoop(runner)
loop.start()  # optional daemon
```

The wrapper host calls `ensure_schedule_runner()` which starts `ScheduleLoop` when the scheduler optional dependency is available.
