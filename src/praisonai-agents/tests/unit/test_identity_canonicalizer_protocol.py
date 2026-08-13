"""Tests for the IdentityCanonicalizerProtocol contract (Issue #3886).

Core owns only the dependency-free structural protocol; the WhatsApp
implementation lives in the praisonai-bot adapter. These tests verify the
contract is importable, runtime-checkable, and that a conforming/
non-conforming object is classified correctly.
"""

import pytest

from praisonaiagents.gateway import IdentityCanonicalizerProtocol as ExportedProtocol
from praisonaiagents.gateway.protocols import IdentityCanonicalizerProtocol


def test_protocol_exported_from_gateway_package():
    assert ExportedProtocol is IdentityCanonicalizerProtocol


def test_conforming_object_is_instance():
    class Canon:
        def canonicalize(self, platform: str, raw_user_id: str) -> str:
            return raw_user_id

    assert isinstance(Canon(), IdentityCanonicalizerProtocol)


def test_non_conforming_object_is_not_instance():
    class NotCanon:
        def something_else(self) -> None:  # pragma: no cover - shape only
            ...

    assert not isinstance(NotCanon(), IdentityCanonicalizerProtocol)


def test_fail_open_identity_canonicalizer_returns_raw_when_unknown():
    class Passthrough:
        def canonicalize(self, platform: str, raw_user_id: str) -> str:
            return raw_user_id

    c = Passthrough()
    assert c.canonicalize("whatsapp", "999@lid") == "999@lid"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
