"""Device-identity handshake contract (Issue #5998)."""

import base64

import pytest

from praisonaiagents.gateway import (
    ConnectErrorCode,
    DeviceAuth,
    DeviceIdentityProtocol,
    FrameDecodeError,
    HelloParams,
    decode_client_frame,
    device_id_from_public_key,
)

PUB = "dGVzdC1wdWJsaWMta2V5"


def _hello(**device):
    block = {
        "device_id": device_id_from_public_key(PUB),
        "public_key": PUB,
        "signature": "sig",
        "signed_at": 1700000000,
        "nonce": "n-1",
    }
    block.update(device)
    return {"type": "hello", "agent_id": "a", "device": block}


def test_hello_without_device_is_unchanged():
    frame = decode_client_frame({"type": "hello", "agent_id": "a"})
    assert isinstance(frame, HelloParams)
    assert frame.device is None


def test_hello_decodes_device():
    frame = decode_client_frame(_hello())
    assert isinstance(frame.device, DeviceAuth)
    assert frame.device.device_id == device_id_from_public_key(PUB)
    assert frame.device.nonce == "n-1"
    assert frame.device.signed_at == 1700000000


def test_spoofed_device_id_is_unauthorized():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame(_hello(device_id="0" * 64))
    assert exc.value.error.code == ConnectErrorCode.AUTH_UNAUTHORIZED


@pytest.mark.parametrize("bad", [
    {"signature": ""},
    {"nonce": None},
    {"signed_at": True},
    {"signed_at": "now"},
    {"signed_at": float("nan")},
    {"signed_at": 1700000000.5},
    {"public_key": "not base64!"},
    {"public_key": "dGVzdC1wdWJsaWMta2V5\n"},
])
def test_malformed_device_rejected(bad):
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame(_hello(**bad))
    assert exc.value.error.code == ConnectErrorCode.CONFIGURATION_ERROR


def test_device_must_be_object():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({"type": "hello", "agent_id": "a", "device": "x"})


def test_wire_format_is_pinned():
    # Literal vectors: changing the fingerprint or signed bytes breaks clients.
    assert device_id_from_public_key(PUB) == (
        "c88e80202a4d650841e48649b4c3f553e48131b415db680476fd0d65632ff2b0"
    )
    d = DeviceAuth(device_id_from_public_key(PUB), PUB, "sig", 1700000000, "n-1")
    assert d.signing_payload("a") == (
        b"praisonai-device-v1\n"
        b"c88e80202a4d650841e48649b4c3f553e48131b415db680476fd0d65632ff2b0\n"
        b"n-1\n1700000000\na"
    )


def test_signing_payload_binds_agent_and_nonce():
    d = decode_client_frame(_hello()).device
    assert d.signing_payload("a") != d.signing_payload("b")
    other = DeviceAuth(d.device_id, d.public_key, d.signature, d.signed_at, "n-2")
    assert d.signing_payload("a") != other.signing_payload("a")


def test_ed25519_round_trip():
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    key = ed.Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    pub = base64.b64encode(raw).decode()
    unsigned = DeviceAuth(device_id_from_public_key(pub), pub, "", 1700000000, "nonce")
    sig = base64.b64encode(key.sign(unsigned.signing_payload("a"))).decode()

    frame = decode_client_frame({
        "type": "hello", "agent_id": "a",
        "device": {**unsigned.__dict__, "signature": sig},
    })
    ed.Ed25519PublicKey.from_public_bytes(base64.b64decode(frame.device.public_key)).verify(
        base64.b64decode(frame.device.signature),
        frame.device.signing_payload(frame.agent_id),
    )


def test_protocol_is_runtime_checkable():
    class Store:
        def issue_challenge(self): return "n"
        def verify(self, device, *, agent_id): return None
        def list_devices(self): return []
        def revoke(self, device_id): return False

    assert isinstance(Store(), DeviceIdentityProtocol)
