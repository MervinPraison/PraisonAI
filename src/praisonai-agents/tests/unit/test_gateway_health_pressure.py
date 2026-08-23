"""Unit tests for gateway saturation/back-pressure telemetry (Issue #4265).

Covers the pure, core-side contract: the frozen :class:`HealthPressure`
dataclass, its JSON shape, and the deterministic :func:`evaluate_pressure`
classifier (``nominal`` / ``elevated`` / ``saturated``). No I/O.
"""

from praisonaiagents.gateway import HealthPressure, evaluate_pressure


def test_defaults_are_nominal():
    p = HealthPressure()
    assert p.pressure == "nominal"
    assert p.admission_max == 0
    assert p.event_loop_lag_p99_ms == 0.0


def test_to_dict_has_closed_shape():
    p = HealthPressure(admission_max=16, admission_in_flight=4, pressure="elevated")
    d = p.to_dict()
    assert d["admission_max"] == 16
    assert d["admission_in_flight"] == 4
    assert d["pressure"] == "elevated"
    assert set(d) == {
        "admission_max",
        "admission_in_flight",
        "admission_queued",
        "admission_shed_total",
        "inbox_pending",
        "outbox_pending",
        "outbox_dead_letter",
        "event_loop_lag_p99_ms",
        "pressure",
    }


def test_empty_is_nominal():
    assert evaluate_pressure().pressure == "nominal"
    assert evaluate_pressure(admission={}).pressure == "nominal"


def test_high_utilisation_is_elevated():
    p = evaluate_pressure(
        admission={"max_concurrent_runs": 10, "in_flight": 8, "queued": 0, "shed": 0}
    )
    assert p.pressure == "elevated"
    assert p.admission_in_flight == 8


def test_below_utilisation_threshold_is_nominal():
    p = evaluate_pressure(
        admission={"max_concurrent_runs": 10, "in_flight": 7, "queued": 0}
    )
    assert p.pressure == "nominal"


def test_full_and_queued_is_saturated():
    p = evaluate_pressure(
        admission={"max_concurrent_runs": 4, "in_flight": 4, "queued": 3, "shed": 1}
    )
    assert p.pressure == "saturated"
    assert p.admission_queued == 3
    assert p.admission_shed_total == 1


def test_dead_letter_forces_saturated():
    p = evaluate_pressure(outbox_dead_letter=1)
    assert p.pressure == "saturated"
    assert p.outbox_dead_letter == 1


def test_backlog_is_elevated():
    assert evaluate_pressure(inbox_pending=5).pressure == "elevated"
    assert evaluate_pressure(outbox_pending=5).pressure == "elevated"


def test_loop_lag_thresholds():
    assert evaluate_pressure(loop_lag_p99_ms=50.0).pressure == "nominal"
    assert evaluate_pressure(loop_lag_p99_ms=150.0).pressure == "elevated"
    assert evaluate_pressure(loop_lag_p99_ms=800.0).pressure == "saturated"


def test_saturated_dominates_elevated():
    p = evaluate_pressure(
        admission={"max_concurrent_runs": 2, "in_flight": 2, "queued": 1},
        inbox_pending=100,
        outbox_pending=50,
    )
    assert p.pressure == "saturated"


def test_tolerates_junk_inputs():
    p = evaluate_pressure(
        admission={"max_concurrent_runs": None, "in_flight": "x"},
        inbox_pending="nope",
        outbox_pending=None,
        outbox_dead_letter=-3,
        loop_lag_p99_ms="bad",
    )
    assert p.pressure == "nominal"
    assert p.admission_max == 0
    assert p.admission_in_flight == 0
    assert p.outbox_dead_letter == 0
    assert p.event_loop_lag_p99_ms == 0.0


def test_unbounded_admission_never_saturates_on_util_alone():
    # No ceiling (max == 0): utilisation is undefined; only queued/backlog/lag
    # can raise pressure, never a divide-by-zero.
    p = evaluate_pressure(admission={"max_concurrent_runs": 0, "in_flight": 999})
    assert p.pressure == "nominal"


def test_is_frozen():
    p = HealthPressure()
    import dataclasses

    try:
        p.pressure = "saturated"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("HealthPressure should be frozen")
