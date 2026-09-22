"""Native Chroma initialization errors must respect memory failure handling."""

import sys
from asyncio import CancelledError
from types import ModuleType
from unittest.mock import Mock

import pytest

from praisonaiagents.memory.adapters.factories import create_chroma_memory_adapter
from praisonaiagents.memory.memory import Memory


class NativePanic(BaseException):
    """Match pyo3's exception hierarchy without requiring its native extension."""


@pytest.fixture(params=["adapter", "legacy"])
def bootstrap(request, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    chroma = ModuleType("chromadb")
    config = ModuleType("chromadb.config")
    config.Settings = Mock()
    chroma.PersistentClient = Mock()
    monkeypatch.setitem(sys.modules, "chromadb", chroma)
    monkeypatch.setitem(sys.modules, "chromadb.config", config)
    path = str(tmp_path / "chroma")
    memory = Memory({"provider": "sqlite", "rag_db_path": path}, verbose=5)
    memory.use_rag = True

    def initialize():
        if request.param == "adapter":
            return create_chroma_memory_adapter(rag_db_path=path)
        memory._init_chroma()
        return memory

    yield request.param, initialize, chroma, config, path
    memory.close_connections()


def test_native_panic_uses_normal_failure_path(bootstrap, caplog):
    kind, initialize, chroma, _, path = bootstrap
    panic = NativePanic("corrupt sqlite store")
    chroma.PersistentClient.side_effect = panic
    if kind == "adapter":
        with pytest.raises(RuntimeError, match="Chroma persist failed") as caught:
            initialize()
        assert caught.value.__cause__ is panic
        assert path in str(caught.value)
        assert "NativePanic" in str(caught.value)
    else:
        memory = initialize()
        assert memory.use_rag is False
        assert "NativePanic" in caplog.text
        assert path in caplog.text


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit, GeneratorExit, CancelledError])
def test_control_flow_signals_propagate(bootstrap, signal):
    _, initialize, chroma, _, _ = bootstrap
    error = signal("stop")
    chroma.PersistentClient.side_effect = error
    with pytest.raises(signal) as caught:
        initialize()
    assert caught.value is error


def test_ordinary_errors_keep_existing_behavior(bootstrap):
    kind, initialize, chroma, _, _ = bootstrap
    error = ValueError("invalid configuration")
    chroma.PersistentClient.side_effect = error
    if kind == "adapter":
        with pytest.raises(ValueError) as caught:
            initialize()
        assert caught.value is error
    else:
        assert initialize().use_rag is False


def test_success_preserves_client_configuration(bootstrap):
    kind, initialize, chroma, config, path = bootstrap
    result = initialize()
    config.Settings.assert_called_once_with(anonymized_telemetry=False, allow_reset=True)
    chroma.PersistentClient.assert_called_once_with(path=path, settings=config.Settings.return_value)
    collection = chroma.PersistentClient.return_value.get_collection.return_value
    assert (result.collection if kind == "adapter" else result.chroma_col) is collection
