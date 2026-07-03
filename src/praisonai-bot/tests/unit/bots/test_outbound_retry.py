#!/usr/bin/env python3
"""
Test script for outbound message retry functionality.
"""

import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch

from praisonai_bot.bots._resilience import (
    deliver_with_retry,
    BackoffPolicy,
    is_recoverable_error,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransientError(Exception):
    """Simulated transient platform error."""
    def __init__(self):
        self.status_code = 503
        super().__init__("Service temporarily unavailable")


class PermanentError(Exception):
    """Simulated permanent error."""
    def __init__(self):
        self.status_code = 400
        super().__init__("Bad request")


async def test_successful_send():
    """Test successful send on first attempt."""
    logger.info("Testing successful send on first attempt...")
    
    send_func = AsyncMock(return_value="message_sent")
    policy = BackoffPolicy(max_attempts=3)
    
    result = await deliver_with_retry(send_func, policy=policy)
    
    assert result == "message_sent"
    assert send_func.call_count == 1
    logger.info("✓ Successful send test passed")


async def test_transient_error_with_retry():
    """Test retry on transient error."""
    logger.info("Testing retry on transient error...")
    
    # Fail twice, then succeed
    send_func = AsyncMock(side_effect=[
        TransientError(),
        TransientError(),
        "message_sent"
    ])
    
    policy = BackoffPolicy(initial_ms=100, max_attempts=3)
    
    result = await deliver_with_retry(send_func, policy=policy)
    
    assert result == "message_sent"
    assert send_func.call_count == 3
    logger.info("✓ Transient error retry test passed")


async def test_permanent_error_no_retry():
    """Test no retry on permanent error."""
    logger.info("Testing no retry on permanent error...")
    
    send_func = AsyncMock(side_effect=PermanentError())
    policy = BackoffPolicy(max_attempts=3)
    
    try:
        await deliver_with_retry(send_func, policy=policy)
        assert False, "Should have raised PermanentError"
    except PermanentError:
        pass
    
    assert send_func.call_count == 1  # Should not retry
    logger.info("✓ Permanent error test passed")


async def test_max_attempts_exceeded():
    """Test failure after max attempts."""
    logger.info("Testing max attempts exceeded...")
    
    send_func = AsyncMock(side_effect=TransientError())
    policy = BackoffPolicy(initial_ms=10, max_attempts=3)
    
    try:
        await deliver_with_retry(send_func, policy=policy)
        assert False, "Should have raised TransientError"
    except TransientError:
        pass
    
    assert send_func.call_count == 3
    logger.info("✓ Max attempts test passed")


async def test_dlq_on_final_failure():
    """Test DLQ enqueue on final failure."""
    logger.info("Testing DLQ enqueue on final failure...")
    
    send_func = AsyncMock(side_effect=TransientError())
    dlq_mock = AsyncMock()
    dlq_mock.enqueue_outbound = AsyncMock()
    
    policy = BackoffPolicy(initial_ms=10, max_attempts=2)
    reply_data = {"channel_id": "123", "reply_text": "Hello"}
    
    try:
        await deliver_with_retry(
            send_func,
            policy=policy,
            platform="test",
            parked_store=dlq_mock,
            reply_data=reply_data
        )
        assert False, "Should have raised TransientError"
    except TransientError:
        pass
    
    assert send_func.call_count == 2
    dlq_mock.enqueue_outbound.assert_called_once()
    call_args = dlq_mock.enqueue_outbound.call_args[1]
    assert call_args["platform"] == "test"
    assert "TransientError" in call_args["error"]
    assert call_args["channel_id"] == "123"
    assert call_args["reply_text"] == "Hello"
    logger.info("✓ DLQ test passed")


async def test_recoverable_error_detection():
    """Test recoverable error detection."""
    logger.info("Testing recoverable error detection...")
    
    # Test common recoverable errors
    assert is_recoverable_error(Exception("connection timeout"))
    assert is_recoverable_error(Exception("rate limit exceeded"))
    assert is_recoverable_error(Exception("internal server error"))
    assert is_recoverable_error(ConnectionError())
    assert is_recoverable_error(asyncio.TimeoutError())
    
    # Test non-recoverable errors
    assert not is_recoverable_error(Exception("user not found"))
    assert not is_recoverable_error(ValueError("invalid input"))
    
    logger.info("✓ Error detection test passed")


async def main():
    """Run all tests."""
    logger.info("Starting outbound retry tests...")
    
    await test_successful_send()
    await test_transient_error_with_retry()
    await test_permanent_error_no_retry()
    await test_max_attempts_exceeded()
    await test_dlq_on_final_failure()
    await test_recoverable_error_detection()
    
    logger.info("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())