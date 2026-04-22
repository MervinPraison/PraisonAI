import pytest
import asyncio
import time
from praisonai.gateway.rate_limiter import AuthRateLimiter
from praisonai.gateway.pairing import PairingStore
from praisonai.gateway.exec_approval import ExecApprovalManager, Resolution
from praisonai.gateway.gateway_approval import GatewayApprovalBackend
from praisonaiagents.approval import ApprovalRequest

from unittest.mock import patch

def test_auth_rate_limiter():
    limiter = AuthRateLimiter(max_attempts=2, window_seconds=1.0, lockout_seconds=1.0)
    
    with patch("time.time") as mock_time:
        mock_time.return_value = 1000.0
        assert limiter.allow("test", "ip1") is True
        assert limiter.allow("test", "ip1") is True
        assert limiter.allow("test", "ip1") is False  # rate limited
        
        # different ip should work
        assert limiter.allow("test", "ip2") is True
        
        # advance time past lockout
        mock_time.return_value = 1001.5
        
        # should be allowed again
        assert limiter.allow("test", "ip1") is True

@pytest.mark.asyncio
async def test_pairing_store():
    store = PairingStore()
    
    # generate code
    code = store.generate_code()
    assert len(code) == 8
    
    # generate a few to fill store
    code2 = store.generate_code()
    
    # simulate user verifying
    device_id = "dev_123"
    result = store.verify_and_pair(code, device_id, "test_channel")
    assert result is True
    
    # verify second time should fail (code consumed)
    assert store.verify_and_pair(code, device_id, "test_channel") is False
    
    # revoke
    store.revoke(device_id, "test_channel")


@pytest.mark.asyncio
async def test_pairing_store_channel_bound_code():
    store = PairingStore()
    code = store.generate_code(channel_type="telegram", channel_id="tg_user_1")

    # Should resolve channel_id from pending code when omitted
    assert store.verify_and_pair(code, None, "telegram") is True
    assert store.is_paired("tg_user_1", "telegram") is True


@pytest.mark.asyncio
async def test_pairing_store_rejects_channel_id_mismatch():
    store = PairingStore()
    code = store.generate_code(channel_type="telegram", channel_id="tg_user_1")

    # Mismatched explicit channel_id must be rejected
    assert store.verify_and_pair(code, "tg_user_2", "telegram") is False

@pytest.mark.asyncio
async def test_exec_approval_manager():
    mgr = ExecApprovalManager()
    
    # Register request
    req_id, future = await mgr.register(tool_name="rm", arguments={"path": "/"}, risk_level="critical")
    assert req_id in mgr._pending
    
    # List pending
    pending = mgr.list_pending()
    assert len(pending) == 1
    assert pending[0]["request_id"] == req_id
    assert pending[0]["tool_name"] == "rm"
    
    # Resolve it
    mgr.resolve(req_id, Resolution(approved=True, reason="Unit test allowed"))
    
    await asyncio.sleep(0.01)
    
    # Check future is resolved
    assert future.done()
    decision = await future
    assert decision.approved is True
    assert decision.reason == "Unit test allowed"
    
    # No pending
    assert len(mgr.list_pending()) == 0

@pytest.mark.asyncio
async def test_gateway_approval_backend():
    mgr = ExecApprovalManager()
    backend = GatewayApprovalBackend(mgr)
    
    req = ApprovalRequest(tool_name="test_tool", arguments={}, risk_level="high")
    
    # Start request in background
    task = asyncio.create_task(backend.request_approval(req))
    
    # Give it a tiny bit to register
    await asyncio.sleep(0.01)
    
    pending = mgr.list_pending()
    assert len(pending) == 1
    req_id = pending[0]["request_id"]
    
    # Resolve
    mgr.resolve(req_id, Resolution(approved=False, reason="Denied by test"))
    
    decision = await task
    assert decision.approved is False
    assert decision.reason == "Denied by test"

@pytest.mark.asyncio
async def test_exec_approval_allowlist():
    mgr = ExecApprovalManager()
    backend = GatewayApprovalBackend(mgr)
    
    # Add to allowlist
    mgr.allowlist.add("safe_tool")
    
    req = ApprovalRequest(tool_name="safe_tool", arguments={}, risk_level="high")
    
    # Should resolve immediately without waiting
    decision = await backend.request_approval(req)
    assert decision.approved is True
    assert decision.reason == "allow-always"

    # Pending shouldn't be populated
    assert len(mgr.list_pending()) == 0
