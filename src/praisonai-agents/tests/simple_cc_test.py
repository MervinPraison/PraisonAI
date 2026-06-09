"""
Simple test for email CC/BCC functionality without pytest dependency.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents.tools.email_tools import _parse_email_list, send_email


def test_email_parsing():
    """Test email address parsing."""
    # Test single email
    assert _parse_email_list("test@example.com") == ["test@example.com"]
    
    # Test comma-separated emails
    result = _parse_email_list("test1@example.com, test2@example.com")
    assert result == ["test1@example.com", "test2@example.com"]
    
    # Test list input
    result = _parse_email_list(["test1@example.com", "test2@example.com"])
    assert result == ["test1@example.com", "test2@example.com"]
    
    # Test empty input
    assert _parse_email_list("") == []
    assert _parse_email_list(None) == []
    
    print("✓ Email parsing tests passed")


def test_function_signatures():
    """Test that functions have CC/BCC parameters."""
    import inspect
    from praisonaiagents.tools.email_tools import send_email, draft_email
    
    # Check send_email signature
    sig = inspect.signature(send_email)
    assert 'cc' in sig.parameters
    assert 'bcc' in sig.parameters
    
    # Check draft_email signature
    sig = inspect.signature(draft_email)
    assert 'cc' in sig.parameters
    assert 'bcc' in sig.parameters
    
    print("✓ Function signature tests passed")


def test_no_backend_error():
    """Test that appropriate error is returned when no backend is configured."""
    # Clear environment variables
    for key in ['AGENTMAIL_API_KEY', 'EMAIL_ADDRESS', 'EMAIL_PASSWORD']:
        os.environ.pop(key, None)
    
    try:
        result = send_email(
            to="test@example.com",
            subject="Test",
            body="Test body",
            cc="cc@example.com",
            bcc="bcc@example.com"
        )
        # Should not reach here
        assert False, "Expected ValueError but got result: " + result
    except ValueError as e:
        assert "No email backend configured" in str(e)
        print("✓ Backend error test passed")


if __name__ == "__main__":
    print("Running simple email CC/BCC tests...")
    
    try:
        test_email_parsing()
        test_function_signatures()
        test_no_backend_error()
        
        print("\n🎉 All tests passed! Email CC/BCC functionality is working.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)