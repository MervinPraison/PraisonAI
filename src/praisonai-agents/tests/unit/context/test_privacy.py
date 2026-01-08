"""
Tests for privacy hardening in context management.

Tests cover:
- Redaction patterns for various API keys
- Path validation for monitor output
- Ignore/include pattern integration
"""

from praisonaiagents.context.monitor import (
    redact_sensitive,
    validate_monitor_path,
    should_include_content,
    load_ignore_patterns,
    SENSITIVE_PATTERNS,
)


class TestRedactionPatterns:
    """Tests for sensitive data redaction."""
    
    def test_redact_openai_key(self):
        """Test OpenAI API key redaction."""
        text = "My key is sk-1234567890abcdefghijklmnop"
        result = redact_sensitive(text)
        assert "sk-1234567890" not in result
        assert "[REDACTED]" in result
    
    def test_redact_openai_project_key(self):
        """Test OpenAI project key redaction."""
        text = "Using sk-proj-abc123_def456-xyz789"
        result = redact_sensitive(text)
        assert "sk-proj-" not in result
        assert "[REDACTED]" in result
    
    def test_redact_anthropic_key(self):
        """Test Anthropic API key redaction."""
        text = "Anthropic key: sk-ant-abc123def456ghi789"
        result = redact_sensitive(text)
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result
    
    def test_redact_anthropic_api_key(self):
        """Test Anthropic API key with version."""
        text = "Key is sk-ant-api03-abcdefghijklmnop"
        result = redact_sensitive(text)
        assert "sk-ant-api" not in result
        assert "[REDACTED]" in result
    
    def test_redact_google_api_key(self):
        """Test Google API key redaction."""
        text = "Google key: AIzaSyAbcdefghijklmnopqrstuvwxyz12345"
        result = redact_sensitive(text)
        assert "AIzaSy" not in result
        assert "[REDACTED]" in result
    
    def test_redact_google_oauth_token(self):
        """Test Google OAuth token redaction."""
        text = "Token: ya29.a0AfH6SMBabcdefghijklmnop"
        result = redact_sensitive(text)
        assert "ya29." not in result
        assert "[REDACTED]" in result
    
    def test_redact_aws_access_key(self):
        """Test AWS access key redaction."""
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = redact_sensitive(text)
        assert "AKIA" not in result
        assert "[REDACTED]" in result
    
    def test_redact_aws_temp_key(self):
        """Test AWS temporary access key redaction."""
        # AWS temp keys are exactly 20 chars: ASIA + 16 alphanumeric
        text = "Temp key: ASIAIOSFODNN7EXAMPLE"
        result = redact_sensitive(text)
        assert "ASIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result
    
    def test_redact_bearer_token(self):
        """Test bearer token redaction."""
        text = "Authorization: Bearer abc123def456"
        result = redact_sensitive(text)
        assert "Bearer abc123" not in result
        assert "[REDACTED]" in result
    
    def test_redact_password_pattern(self):
        """Test password pattern redaction."""
        text = 'password = "mysecretpassword123"'
        result = redact_sensitive(text)
        assert "mysecretpassword" not in result
        assert "[REDACTED]" in result
    
    def test_redact_api_key_pattern(self):
        """Test generic API key pattern redaction."""
        text = 'api_key: "abc123def456"'
        result = redact_sensitive(text)
        assert "abc123def456" not in result
        assert "[REDACTED]" in result
    
    def test_preserves_normal_text(self):
        """Test that normal text is preserved."""
        text = "Hello, this is a normal message without secrets."
        result = redact_sensitive(text)
        assert result == text
    
    def test_multiple_redactions(self):
        """Test multiple sensitive items in one text."""
        text = "Keys: sk-abc123def456ghi789jkl, sk-ant-xyz789"
        result = redact_sensitive(text)
        assert "sk-abc" not in result
        assert "sk-ant" not in result
        assert result.count("[REDACTED]") >= 2


class TestPathValidation:
    """Tests for monitor path validation."""
    
    def test_valid_relative_path(self):
        """Test valid relative path."""
        is_valid, error = validate_monitor_path("./context.txt")
        assert is_valid is True
        assert error == ""
    
    def test_valid_simple_filename(self):
        """Test simple filename."""
        is_valid, error = validate_monitor_path("context.txt")
        assert is_valid is True
        assert error == ""
    
    def test_path_traversal_blocked(self):
        """Test path traversal is blocked."""
        is_valid, error = validate_monitor_path("../../../etc/passwd")
        assert is_valid is False
        assert "traversal" in error.lower()
    
    def test_absolute_path_blocked_by_default(self):
        """Test absolute paths blocked by default."""
        is_valid, error = validate_monitor_path("/tmp/context.txt")
        assert is_valid is False
        assert "absolute" in error.lower()
    
    def test_absolute_path_allowed_when_enabled(self):
        """Test absolute paths allowed when explicitly enabled."""
        is_valid, error = validate_monitor_path(
            "/tmp/context.txt",
            allow_absolute=True,
        )
        assert is_valid is True
    
    def test_suspicious_path_blocked(self):
        """Test suspicious paths are blocked."""
        is_valid, error = validate_monitor_path("/etc/passwd")
        assert is_valid is False
    
    def test_home_path_blocked(self):
        """Test home directory paths blocked by default."""
        is_valid, error = validate_monitor_path("/home/user/file.txt")
        assert is_valid is False


class TestIgnoreIncludePatterns:
    """Tests for ignore/include pattern handling."""
    
    def test_include_all_by_default(self):
        """Test all files included by default."""
        result = should_include_content("test.py")
        assert result is True
    
    def test_ignore_pattern_match(self):
        """Test ignore pattern matching."""
        result = should_include_content(
            "secret.key",
            ignore_patterns=["*.key", "*.pem"],
        )
        assert result is False
    
    def test_ignore_pattern_no_match(self):
        """Test ignore pattern not matching."""
        result = should_include_content(
            "code.py",
            ignore_patterns=["*.key", "*.pem"],
        )
        assert result is True
    
    def test_include_pattern_whitelist(self):
        """Test include pattern as whitelist."""
        result = should_include_content(
            "code.py",
            include_patterns=["*.py", "*.js"],
        )
        assert result is True
    
    def test_include_pattern_excludes_others(self):
        """Test include pattern excludes non-matching."""
        result = should_include_content(
            "data.json",
            include_patterns=["*.py", "*.js"],
        )
        assert result is False
    
    def test_ignore_overrides_include(self):
        """Test ignore patterns override include."""
        result = should_include_content(
            "secret.py",
            include_patterns=["*.py"],
            ignore_patterns=["secret*"],
        )
        assert result is False
    
    def test_path_pattern_match(self):
        """Test full path pattern matching."""
        result = should_include_content(
            "/path/to/node_modules/file.js",
            ignore_patterns=["*node_modules*"],
        )
        assert result is False


class TestSensitivePatternsCoverage:
    """Tests to ensure all expected patterns are covered."""
    
    def test_patterns_list_not_empty(self):
        """Test patterns list is populated."""
        assert len(SENSITIVE_PATTERNS) > 0
    
    def test_openai_patterns_present(self):
        """Test OpenAI patterns are in list."""
        patterns_str = str(SENSITIVE_PATTERNS)
        assert "sk-" in patterns_str
    
    def test_anthropic_patterns_present(self):
        """Test Anthropic patterns are in list."""
        patterns_str = str(SENSITIVE_PATTERNS)
        assert "sk-ant" in patterns_str
    
    def test_google_patterns_present(self):
        """Test Google patterns are in list."""
        patterns_str = str(SENSITIVE_PATTERNS)
        assert "AIza" in patterns_str
    
    def test_aws_patterns_present(self):
        """Test AWS patterns are in list."""
        patterns_str = str(SENSITIVE_PATTERNS)
        assert "AKIA" in patterns_str
    
    def test_bearer_pattern_present(self):
        """Test bearer token pattern is in list."""
        patterns_str = str(SENSITIVE_PATTERNS)
        assert "bearer" in patterns_str.lower()
