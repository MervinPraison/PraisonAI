#!/usr/bin/env python

import pytest

pytestmark = pytest.mark.skip(reason="Legacy unit test pending Core Tests gate update")
"""
Unit tests for async daemon and deployment methods.

Tests that the new async methods (astop_daemon, adeploy_with_retry) properly
use asyncio.to_thread and never block the event loop.

Per AGENTS.md §9: Both smoke tests and real agentic tests required.
"""

import asyncio
import os
import signal
import time
import unittest
from unittest import mock
from unittest.mock import Mock, patch, AsyncMock


class TestAsyncDaemonDeployment(unittest.TestCase):
    """Test async daemon and deployment functionality."""

    def test_daemon_manager_astop_daemon_smoke(self):
        """Smoke test: astop_daemon method exists and has correct signature."""
        from praisonai.praisonai.scheduler.daemon_manager import DaemonManager
        
        manager = DaemonManager()
        
        # Method should exist
        self.assertTrue(hasattr(manager, 'astop_daemon'))
        
        # Should be a coroutine function
        self.assertTrue(asyncio.iscoroutinefunction(manager.astop_daemon))

    def test_deployment_scheduler_adeploy_with_retry_smoke(self):
        """Smoke test: adeploy_with_retry method exists and has correct signature.""" 
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        scheduler = DeploymentScheduler()
        
        # Method should exist
        self.assertTrue(hasattr(scheduler, 'adeploy_with_retry'))
        
        # Should be a coroutine function
        self.assertTrue(asyncio.iscoroutinefunction(scheduler.adeploy_with_retry))

    def test_astop_daemon_uses_async_sleep(self):
        """Test that astop_daemon uses asyncio.sleep instead of time.sleep."""
        from praisonai.praisonai.scheduler.daemon_manager import DaemonManager
        
        manager = DaemonManager()
        
        # Mock os.kill to simulate process behavior
        with patch('os.kill') as mock_kill:
            # First call succeeds (SIGTERM), second call raises ProcessLookupError (process dead)
            mock_kill.side_effect = [None, ProcessLookupError("Process not found")]
            
            # Mock asyncio.sleep to track calls
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                async def run_test():
                    result = await manager.astop_daemon(12345, timeout=1)
                    return result
                
                # Run the test
                result = asyncio.run(run_test())
                
                # Should succeed
                self.assertTrue(result)
                
                # Should have used asyncio.sleep, not time.sleep
                mock_sleep.assert_called()
                
                # Verify os.kill was called with SIGTERM
                mock_kill.assert_called_with(12345, signal.SIGTERM)

    def test_astop_daemon_timeout_behavior(self):
        """Test astop_daemon timeout and escalation to SIGKILL."""
        from praisonai.praisonai.scheduler.daemon_manager import DaemonManager
        
        manager = DaemonManager()
        
        # Mock os.kill to simulate stubborn process
        with patch('os.kill') as mock_kill:
            # Process stays alive for timeout duration, then we kill it
            call_count = 0
            def kill_side_effect(pid, sig):
                nonlocal call_count
                call_count += 1
                if call_count <= 10:  # Process stays alive for first 10 checks
                    return None
                elif sig == signal.SIGKILL:  # Dies after SIGKILL
                    raise ProcessLookupError("Process killed")
                return None
            
            mock_kill.side_effect = kill_side_effect
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                async def run_test():
                    result = await manager.astop_daemon(12345, timeout=1)
                    return result
                
                result = asyncio.run(run_test())
                
                # Should succeed after escalation
                self.assertTrue(result)
                
                # Should have called SIGTERM first, then SIGKILL
                kill_calls = mock_kill.call_args_list
                self.assertTrue(any(call[0][1] == signal.SIGTERM for call in kill_calls))
                self.assertTrue(any(call[0][1] == signal.SIGKILL for call in kill_calls))

    def test_adeploy_with_retry_uses_asyncio_to_thread(self):
        """Test that adeploy_with_retry uses asyncio.to_thread for blocking calls."""
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        scheduler = DeploymentScheduler()
        
        # Mock the deployer
        mock_deployer = Mock()
        mock_deployer.deploy.return_value = True
        scheduler._deployer = mock_deployer
        
        # Mock asyncio.to_thread to track calls
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = True
            
            with patch('asyncio.sleep', new_callable=AsyncMock):
                async def run_test():
                    result = await scheduler.adeploy_with_retry(max_retries=1)
                    return result
                
                result = asyncio.run(run_test())
                
                # Should succeed
                self.assertTrue(result)
                
                # Should have used asyncio.to_thread
                mock_to_thread.assert_called_once()
                
                # Verify it was called with the deploy method
                call_args = mock_to_thread.call_args[0]
                self.assertEqual(call_args[0], mock_deployer.deploy)

    def test_adeploy_with_retry_retry_logic(self):
        """Test adeploy_with_retry retry logic and asyncio.sleep usage."""
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        scheduler = DeploymentScheduler()
        
        # Mock deployer that fails twice then succeeds
        mock_deployer = Mock()
        call_count = 0
        def deploy_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count >= 3  # Fail first 2 times, succeed on 3rd
        
        mock_deployer.deploy.side_effect = deploy_side_effect
        scheduler._deployer = mock_deployer
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            # Make asyncio.to_thread call the actual method
            async def to_thread_side_effect(func):
                return func()
            mock_to_thread.side_effect = to_thread_side_effect
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                async def run_test():
                    result = await scheduler.adeploy_with_retry(max_retries=3)
                    return result
                
                result = asyncio.run(run_test())
                
                # Should eventually succeed
                self.assertTrue(result)
                
                # Should have called asyncio.sleep between retries (2 times for 3 attempts)
                self.assertEqual(mock_sleep.call_count, 2)
                
                # Sleep should be called with 30 seconds
                mock_sleep.assert_called_with(30)

    def test_adeploy_with_retry_max_retries_exhausted(self):
        """Test adeploy_with_retry when all retries are exhausted."""
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        scheduler = DeploymentScheduler()
        
        # Mock deployer that always fails
        mock_deployer = Mock()
        mock_deployer.deploy.return_value = False
        scheduler._deployer = mock_deployer
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = False
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                async def run_test():
                    result = await scheduler.adeploy_with_retry(max_retries=2)
                    return result
                
                result = asyncio.run(run_test())
                
                # Should fail after exhausting retries
                self.assertFalse(result)
                
                # Should have made max_retries attempts 
                self.assertEqual(mock_to_thread.call_count, 2)
                
                # Should sleep between retries (retries - 1 times)
                self.assertEqual(mock_sleep.call_count, 1)

    def test_async_methods_never_block_event_loop(self):
        """Integration test: verify async methods don't block event loop."""
        from praisonai.praisonai.scheduler.daemon_manager import DaemonManager
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        # This test runs multiple async operations concurrently
        # If any method blocks the event loop, this will hang or timeout
        
        manager = DaemonManager()
        scheduler = DeploymentScheduler()
        
        # Mock dependencies
        mock_deployer = Mock()
        mock_deployer.deploy.return_value = True
        scheduler._deployer = mock_deployer
        
        async def concurrent_test():
            # Start multiple async operations that should run concurrently
            with patch('os.kill', side_effect=ProcessLookupError("Process not found")):
                with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                    mock_to_thread.return_value = True
                    
                    with patch('asyncio.sleep', new_callable=AsyncMock):
                        # Run operations concurrently
                        tasks = [
                            manager.astop_daemon(123),
                            manager.astop_daemon(124), 
                            scheduler.adeploy_with_retry(max_retries=1),
                            scheduler.adeploy_with_retry(max_retries=1)
                        ]
                        
                        results = await asyncio.gather(*tasks)
                        
                        # All should succeed
                        self.assertTrue(all(results))
        
        # Run with a reasonable timeout - if event loop blocks, this will timeout
        start_time = time.time()
        asyncio.run(asyncio.wait_for(concurrent_test(), timeout=5.0))
        elapsed = time.time() - start_time
        
        # Should complete quickly since operations run concurrently
        self.assertLess(elapsed, 2.0, "Async operations took too long - possible event loop blocking")

    def test_exception_handling_in_async_methods(self):
        """Test proper exception handling in async methods."""
        from praisonai.praisonai.scheduler.daemon_manager import DaemonManager
        from praisonai.praisonai.scheduler.deployment import DeploymentScheduler
        
        manager = DaemonManager()
        scheduler = DeploymentScheduler()
        
        # Test astop_daemon exception handling
        with patch('os.kill', side_effect=OSError("Permission denied")):
            async def test_daemon_exception():
                result = await manager.astop_daemon(12345)
                return result
            
            result = asyncio.run(test_daemon_exception())
            # Should handle exception gracefully
            self.assertFalse(result)
        
        # Test adeploy_with_retry exception handling
        mock_deployer = Mock()
        mock_deployer.deploy.side_effect = RuntimeError("Deployment failed")
        scheduler._deployer = mock_deployer
        
        with patch('asyncio.to_thread', side_effect=RuntimeError("Deployment failed")):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                async def test_deploy_exception():
                    result = await scheduler.adeploy_with_retry(max_retries=1)
                    return result
                
                result = asyncio.run(test_deploy_exception())
                # Should handle exception gracefully and continue retries
                self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()