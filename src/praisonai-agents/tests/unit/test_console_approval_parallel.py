"""Console approval requests must not compete for the same terminal input."""
import threading
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.approval.backends import ConsoleBackend


def test_console_prompts_from_distinct_backends_are_serialized(monkeypatch):
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def prompt(self, request):
        if request == "first":
            first_entered.set()
            assert release_first.wait(5)
        else:
            second_entered.set()
        return True, "once", None, None

    monkeypatch.setattr(ConsoleBackend, "_prompt_user", prompt)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(ConsoleBackend().request_approval_sync, "first")
        assert first_entered.wait(5)
        second = pool.submit(ConsoleBackend().request_approval_sync, "second")
        try:
            assert not second_entered.wait(0.2)
        finally:
            release_first.set()
        assert first.result(timeout=5).approved
        assert second.result(timeout=5).approved
        assert second_entered.is_set()
