"""/tasks over BackgroundJobManager jobs (background subagents, #6037)."""

import threading

from praisonaiagents.background import BackgroundRunner
from praisonaiagents.background.job_manager import BackgroundJobManager

from praisonai_bot.bots._commands import handle_tasks_command


def _start(jm, owner, release):
    return jm.start_job(
        release.wait,
        origin={"deliver": "origin", "user_id": owner, "task": "research repo"},
    )


def test_list_detail_and_cancel_own_jobs():
    jm = BackgroundJobManager()
    release = threading.Event()
    try:
        mine = _start(jm, "alice", release)
        theirs = _start(jm, "bob", release)
        runner = BackgroundRunner()

        listing = handle_tasks_command("alice", None, runner=runner, job_manager=jm)
        assert mine in listing
        assert "research repo" in listing
        assert theirs not in listing

        detail = handle_tasks_command("alice", mine, runner=runner, job_manager=jm)
        assert mine in detail

        assert "not found" in handle_tasks_command(
            "alice", theirs, runner=runner, job_manager=jm
        )
        assert "not found" in handle_tasks_command(
            "alice", f"cancel {theirs}", runner=runner, job_manager=jm
        )

        out = handle_tasks_command("alice", f"cancel {mine}", runner=runner, job_manager=jm)
        assert out.startswith("✅")
        assert jm.get_job_info(mine).status.value == "cancelled"
        assert jm.get_job_info(theirs).status.value == "running"
    finally:
        release.set()
        jm.shutdown()


def test_ownerless_jobs_hidden():
    jm = BackgroundJobManager()
    try:
        job = jm.start_job(lambda: "x")
        jm.get_result(job, timeout=5)
        out = handle_tasks_command("alice", None, runner=BackgroundRunner(), job_manager=jm)
        assert out == "💤 No background tasks."
    finally:
        jm.shutdown()
