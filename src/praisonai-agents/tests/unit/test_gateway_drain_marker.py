"""Unit tests for the port-less, restart-safe external drain trigger (Issue #2390).

Covers the pure, core-side decision predicate ``DrainMarkerPolicy`` and the
``current_epoch`` instantiation-identity helper.
"""

from praisonaiagents.gateway import DrainMarkerPolicy, current_epoch


def test_missing_marker_is_not_a_request():
    policy = DrainMarkerPolicy()
    assert policy.drain_requested(None, "epoch-1", 0.0) is False


def test_non_dict_marker_is_not_a_request():
    policy = DrainMarkerPolicy()
    assert policy.drain_requested("drain", "epoch-1", 0.0) is False  # type: ignore[arg-type]


def test_current_epoch_marker_is_honoured():
    policy = DrainMarkerPolicy()
    marker = {"epoch": "epoch-1", "action": "drain"}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is True


def test_stale_foreign_epoch_marker_is_ignored():
    policy = DrainMarkerPolicy()
    marker = {"epoch": "old-epoch", "action": "drain"}
    # A marker that survived a reboot/restart on a durable volume.
    assert policy.drain_requested(marker, "new-epoch", 0.0) is False


def test_marker_without_epoch_is_ignored_by_default():
    policy = DrainMarkerPolicy()
    marker = {"action": "drain"}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is False


def test_marker_without_epoch_honoured_when_not_required():
    policy = DrainMarkerPolicy(require_epoch=False)
    marker = {"action": "drain"}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is True


def test_action_defaults_to_drain_when_absent():
    policy = DrainMarkerPolicy()
    marker = {"epoch": "epoch-1"}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is True


def test_unknown_action_is_ignored():
    policy = DrainMarkerPolicy()
    marker = {"epoch": "epoch-1", "action": "pause"}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is False


def test_non_string_action_is_ignored():
    policy = DrainMarkerPolicy()
    # A malformed marker with a non-string action must fail closed.
    marker = {"epoch": "epoch-1", "action": 1}
    assert policy.drain_requested(marker, "epoch-1", 0.0) is False


def test_last_handled_epoch_dedupes_request():
    policy = DrainMarkerPolicy()
    marker = {"epoch": "epoch-1", "action": "drain"}
    # First read fires.
    assert policy.drain_requested(marker, "epoch-1", 0.0) is True
    # A repeated read for the same instantiation is suppressed.
    assert (
        policy.drain_requested(
            marker, "epoch-1", 1.0, last_handled_epoch="epoch-1"
        )
        is False
    )


def test_current_epoch_is_stable_within_process():
    first = current_epoch()
    second = current_epoch()
    assert first == second
    assert isinstance(first, str)
