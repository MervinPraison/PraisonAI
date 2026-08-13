"""Import-time behavior for the lazy inbuilt-tools namespace."""

import importlib
import sys


def test_inbuilt_tools_only_probes_its_actual_optional_package(monkeypatch):
    import praisonai._framework_availability as availability

    calls = []

    def fake_is_available(package):
        calls.append(package)
        return False

    monkeypatch.setattr(availability, "is_available", fake_is_available)
    package = importlib.import_module("praisonai")
    monkeypatch.delitem(sys.modules, "praisonai.inbuilt_tools", raising=False)
    monkeypatch.delattr(package, "inbuilt_tools", raising=False)

    module = importlib.import_module("praisonai.inbuilt_tools")

    assert calls == ["praisonai_tools"]
    assert "CREWAI_AVAILABLE" not in module.__dict__
    assert "AUTOGEN_AVAILABLE" not in module.__dict__
    assert module.PRAISONAI_TOOLS_PACKAGE_AVAILABLE is False
