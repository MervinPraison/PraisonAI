"""Tests for the optional progress_callback on generate_dataset.

Network is stubbed out (``_call`` is monkeypatched) so these run offline and
deterministically — we only exercise the progress-reporting contract.
"""
from praisonai_train.data import generate as gen_mod
from praisonai_train.data.generate import generate_dataset


def _cfg(n):
    return {"endpoint": "http://x", "api_key": "k", "deployment": "d", "num_examples": n,
            "concurrency": 4, "stop_file": "/nonexistent/stop"}


def _fake_call(cfg, spec):
    # One unique row per prompt spec so dedup keeps them all.
    return {"instruction": spec["user"], "input": "", "output": "ஒரு முழுமையான தமிழ் பதில் இங்கே."}


def test_progress_callback_monotonic_to_total(monkeypatch):
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    n = 12
    calls = []
    rows = list(generate_dataset(_cfg(n), progress_callback=lambda d, t, k: calls.append((d, t, k))))

    assert calls, "callback should fire at least once"
    dones = [d for d, _, _ in calls]
    kepts = [k for _, _, k in calls]
    totals = {t for _, t, _ in calls}

    assert totals == {n}                       # total is stable and equals the spec count
    assert dones == sorted(dones)              # done is monotonic non-decreasing
    assert kepts == sorted(kepts)              # kept is monotonic non-decreasing
    assert dones[0] == 0                       # fires once up-front with done=0
    assert dones[-1] == n                       # reaches total when the run completes
    assert kepts[-1] == len(rows) == n          # final kept matches emitted rows
    assert all(k <= d for d, _, k in calls)     # never more kept than done


def test_progress_callback_optional_default_none(monkeypatch):
    # Backward compatible: no callback => original behaviour, still yields rows.
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    rows = list(generate_dataset(_cfg(5)))
    assert len(rows) == 5


def test_progress_kept_tracks_dedup(monkeypatch):
    # When the teacher returns duplicates, done keeps climbing but kept plateaus.
    monkeypatch.setattr(gen_mod, "_call",
                        lambda cfg, spec: {"instruction": "same", "input": "",
                                           "output": "ஒரு முழுமையான தமிழ் பதில் இங்கே."})
    calls = []
    rows = list(generate_dataset(_cfg(8), progress_callback=lambda d, t, k: calls.append((d, t, k))))
    assert len(rows) == 1                       # dedup collapses to one row
    assert calls[-1][0] == 8                     # done still reaches total
    assert calls[-1][2] == 1                     # kept stays at 1
