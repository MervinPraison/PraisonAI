"""Unit tests for the global operator emergency-stop brake (Issue #4220).

Covers the pure, core-side contract: the ``EmergencyStopProtocol``, the
zero-cost ``NullEmergencyStop`` default (never engaged), the durable
fail-safe ``FileEmergencyStop`` sentinel, and the ``EmergencyStopConfig``
selector wired into ``GatewayConfig``.
"""

import pytest

from praisonaiagents.gateway import (
    EmergencyStopConfig,
    EmergencyStopProtocol,
    EmergencyStopState,
    FileEmergencyStop,
    GatewayConfig,
    NullEmergencyStop,
)


def test_null_and_file_conform_to_protocol():
    assert isinstance(NullEmergencyStop(), EmergencyStopProtocol)
    assert isinstance(FileEmergencyStop("/tmp/x.pause"), EmergencyStopProtocol)


def test_null_brake_never_engaged():
    brake = NullEmergencyStop()
    assert brake.is_engaged() is False
    brake.engage(reason="cost spike", actor="op")
    assert brake.is_engaged() is False
    assert brake.state().engaged is False


def test_file_brake_engage_disengage_roundtrip(tmp_path):
    sentinel = tmp_path / "gateway.pause"
    brake = FileEmergencyStop(str(sentinel))
    assert brake.is_engaged() is False

    brake.engage(reason="provider incident", actor="mervin")
    assert brake.is_engaged() is True
    st = brake.state()
    assert st.engaged is True
    assert st.reason == "provider incident"
    assert st.actor == "mervin"
    assert st.at > 0

    brake.disengage()
    assert brake.is_engaged() is False
    assert brake.state().engaged is False


def test_file_brake_is_durable_across_instances(tmp_path):
    sentinel = tmp_path / "gateway.pause"
    FileEmergencyStop(str(sentinel)).engage(reason="hold")
    # A fresh instance (as after a restart) sees the persisted engaged state.
    assert FileEmergencyStop(str(sentinel)).is_engaged() is True


def test_file_brake_disengage_is_idempotent(tmp_path):
    brake = FileEmergencyStop(str(tmp_path / "gateway.pause"))
    brake.disengage()  # no sentinel yet -> no error
    assert brake.is_engaged() is False


def test_file_brake_corrupt_sentinel_fails_safe_engaged(tmp_path):
    sentinel = tmp_path / "gateway.pause"
    sentinel.write_text("{ this is not valid json")
    brake = FileEmergencyStop(str(sentinel))
    # Unreadable/corrupt sentinel counts as engaged, never "run freely".
    assert brake.is_engaged() is True
    assert brake.state().engaged is True


def test_file_brake_requires_path():
    with pytest.raises(ValueError):
        FileEmergencyStop("")


def test_config_defaults_off_and_disabled():
    cfg = EmergencyStopConfig()
    assert cfg.backend == "off"
    assert cfg.enabled is False
    assert isinstance(cfg.to_estop(), NullEmergencyStop)


def test_config_file_backend_requires_path():
    with pytest.raises(ValueError):
        EmergencyStopConfig(backend="file")


def test_config_rejects_unknown_backend():
    with pytest.raises(ValueError):
        EmergencyStopConfig(backend="bogus")


def test_config_file_backend_builds_file_brake(tmp_path):
    cfg = EmergencyStopConfig(backend="file", path=str(tmp_path / "p.pause"))
    assert cfg.enabled is True
    assert isinstance(cfg.to_estop(), FileEmergencyStop)


def test_config_from_dict_tolerates_none():
    assert EmergencyStopConfig.from_dict(None).backend == "off"


def test_config_roundtrip_dict(tmp_path):
    cfg = EmergencyStopConfig(backend="file", path=str(tmp_path / "p.pause"))
    restored = EmergencyStopConfig.from_dict(cfg.to_dict())
    assert restored.backend == "file"
    assert restored.path == cfg.path


def test_gateway_config_default_control_is_off():
    gw = GatewayConfig()
    assert gw.control.backend == "off"
    assert gw.control.enabled is False
    assert gw.to_dict()["control"] == {"backend": "off", "path": None}


def test_estop_state_to_dict():
    state = EmergencyStopState(engaged=True, reason="r", actor="a", at=1.5)
    assert state.to_dict() == {
        "engaged": True,
        "reason": "r",
        "actor": "a",
        "at": 1.5,
    }
