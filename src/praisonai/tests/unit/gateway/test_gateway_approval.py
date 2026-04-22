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


@pytest.mark.asyncio
async def test_pending_persists_across_instances():
    """Pending codes should survive PairingStore recreation (cross-process test)."""
    import tempfile
    import os
    
    # Create temporary directory for this test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Instance A generates a code (no explicit secret - uses persisted secret file)
        store_a = PairingStore(store_dir=tmpdir)
        code = store_a.generate_code(channel_type="telegram", channel_id="tg_42")
        assert len(code) == 8
        
        # Instance B (simulating CLI in separate process) should see the pending code
        store_b = PairingStore(store_dir=tmpdir)
        pending = store_b.list_pending()
        assert len(pending) == 1
        assert pending[0]["code"] == code
        assert pending[0]["channel_type"] == "telegram"
        assert pending[0]["channel_id"] == "tg_42"


@pytest.mark.asyncio 
async def test_secret_persists_across_instances():
    """Two PairingStore instances with same dir should be able to verify each other's codes."""
    import tempfile
    import os
    import stat
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Instance A generates a code (no explicit secret)
        store_a = PairingStore(store_dir=tmpdir)
        code = store_a.generate_code(channel_type="telegram", channel_id="tg_secret_test")
        
        # Verify .gateway_secret file was created with correct permissions
        secret_path = os.path.join(tmpdir, ".gateway_secret")
        assert os.path.exists(secret_path)
        mode = stat.S_IMODE(os.stat(secret_path).st_mode)
        assert mode == 0o600
        
        # Instance B should be able to verify the code (shared secret from file)
        store_b = PairingStore(store_dir=tmpdir)
        result = store_b.verify_and_pair(code, None, "telegram")
        assert result is True
        assert store_b.is_paired("tg_secret_test", "telegram") is True


@pytest.mark.asyncio
async def test_cli_approve_e2e():
    """Test CLI pairing approve command end-to-end."""
    import tempfile
    from typer.testing import CliRunner
    from praisonai.cli.commands.pairing import app as pairing_app
    
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Seed a PairingStore with a bound code (uses persisted secret file)
        store = PairingStore(store_dir=tmpdir)
        code = store.generate_code(channel_type="telegram", channel_id="tg_test")
        
        # Invoke CLI approve (2-arg form, no explicit channel_id)
        result = runner.invoke(pairing_app, [
            "approve", "telegram", code, "--store-dir", tmpdir
        ])
        
        # Should succeed
        assert result.exit_code == 0
        
        # Verify the channel is now paired (fresh instance uses same secret file)
        fresh_store = PairingStore(store_dir=tmpdir)
        assert fresh_store.is_paired("tg_test", "telegram") is True


@pytest.mark.asyncio
async def test_cli_approve_invalid_code():
    """CLI approve should exit non-zero for invalid codes and leave store unchanged."""
    import tempfile
    from typer.testing import CliRunner
    from praisonai.cli.commands.pairing import app as pairing_app
    
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create empty store (uses persisted secret file)
        store = PairingStore(store_dir=tmpdir)
        initial_paired = len(store.list_paired())
        
        # Try to approve nonexistent code
        result = runner.invoke(pairing_app, [
            "approve", "telegram", "deadbeef", "--store-dir", tmpdir
        ])
        
        # Should fail
        assert result.exit_code != 0
        output = (result.stdout or "") + (result.stderr or "")
        assert "invalid" in output.lower() or "expired" in output.lower()
        
        # Store should be unchanged (fresh instance uses same secret file)
        fresh_store = PairingStore(store_dir=tmpdir)
        assert len(fresh_store.list_paired()) == initial_paired


@pytest.mark.asyncio
async def test_cli_approve_survives_restart():
    """Generate code, drop instance, create fresh one, approve should succeed."""
    import tempfile
    from typer.testing import CliRunner
    from praisonai.cli.commands.pairing import app as pairing_app
    
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate code and drop the instance (uses persisted secret file)
        store = PairingStore(store_dir=tmpdir)
        code = store.generate_code(channel_type="telegram", channel_id="tg_restart")
        del store  # Explicitly drop the instance to simulate restart
        
        # Fresh instance should be able to approve the code (same secret file)
        result = runner.invoke(pairing_app, [
            "approve", "telegram", code, "--store-dir", tmpdir
        ])
        
        # Should succeed
        assert result.exit_code == 0
        
        # Verify pairing persisted (fresh instance uses same secret file)
        final_store = PairingStore(store_dir=tmpdir)
        assert final_store.is_paired("tg_restart", "telegram") is True
