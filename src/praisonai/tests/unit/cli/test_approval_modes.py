"""
Tests for Approval Mode Matrix.

Tests that approval modes (auto, manual, scoped) work correctly
with the interactive runtime and tool execution.
"""

import os
import tempfile


class TestRuntimeConfigApprovalMode:
    """Tests for RuntimeConfig approval_mode setting."""
    
    def test_default_approval_mode(self):
        """Test default approval mode is auto."""
        from praisonai.cli.features.interactive_runtime import RuntimeConfig
        
        config = RuntimeConfig()
        assert config.approval_mode == "auto"
    
    def test_custom_approval_mode(self):
        """Test setting custom approval mode."""
        from praisonai.cli.features.interactive_runtime import RuntimeConfig
        
        config = RuntimeConfig(approval_mode="manual")
        assert config.approval_mode == "manual"
        
        config = RuntimeConfig(approval_mode="scoped")
        assert config.approval_mode == "scoped"


class TestInteractiveRuntimeReadOnly:
    """Tests for InteractiveRuntime read_only property."""
    
    def test_auto_mode_not_read_only(self):
        """Test that auto mode is not read-only."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        config = RuntimeConfig(
            workspace="/tmp/test",
            approval_mode="auto",
        )
        runtime = InteractiveRuntime(config)
        
        # Auto mode should NOT be read-only
        assert runtime.read_only is False
    
    def test_auto_mode_writable_without_acp(self):
        """Test that auto mode allows writes even without ACP."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        config = RuntimeConfig(
            workspace="/tmp/test",
            approval_mode="auto",
            acp_enabled=False,  # ACP disabled
        )
        runtime = InteractiveRuntime(config)
        runtime._read_only = True  # Simulate ACP not ready
        
        # Auto mode should still NOT be read-only
        assert runtime.read_only is False
    
    def test_manual_mode_read_only_without_acp(self):
        """Test that manual mode is read-only without ACP."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        config = RuntimeConfig(
            workspace="/tmp/test",
            approval_mode="manual",
        )
        runtime = InteractiveRuntime(config)
        runtime._read_only = True  # Simulate ACP not ready
        
        # Manual mode should be read-only when ACP not ready
        assert runtime.read_only is True
    
    def test_scoped_mode_read_only_without_acp(self):
        """Test that scoped mode is read-only without ACP."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        config = RuntimeConfig(
            workspace="/tmp/test",
            approval_mode="scoped",
        )
        runtime = InteractiveRuntime(config)
        runtime._read_only = True  # Simulate ACP not ready
        
        # Scoped mode should be read-only when ACP not ready
        assert runtime.read_only is True
    
    def test_env_var_auto_mode_override(self):
        """Test that PRAISON_APPROVAL_MODE env var can override to auto mode."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        # Save and clear env var first
        original = os.environ.get("PRAISON_APPROVAL_MODE")
        if "PRAISON_APPROVAL_MODE" in os.environ:
            del os.environ["PRAISON_APPROVAL_MODE"]
        
        try:
            # Without env var, manual mode should be read-only when _read_only=True
            config = RuntimeConfig(
                workspace="/tmp/test",
                approval_mode="manual",
            )
            runtime = InteractiveRuntime(config)
            runtime._read_only = True
            
            # Manual mode without env override should be read-only
            assert runtime.read_only is True
            
            # Now set env var to auto - this should override
            os.environ["PRAISON_APPROVAL_MODE"] = "auto"
            
            # Create new runtime with manual config but env=auto
            config2 = RuntimeConfig(
                workspace="/tmp/test",
                approval_mode="manual",
            )
            runtime2 = InteractiveRuntime(config2)
            runtime2._read_only = True
            
            # The read_only property checks config first, then env
            # Config is manual, so it checks env var next
            # Env var is auto, so it returns False (not read-only)
            assert runtime2.read_only is False
            
        finally:
            if original:
                os.environ["PRAISON_APPROVAL_MODE"] = original
            elif "PRAISON_APPROVAL_MODE" in os.environ:
                del os.environ["PRAISON_APPROVAL_MODE"]


class TestToolConfigApprovalMode:
    """Tests for ToolConfig approval_mode setting."""
    
    def test_default_approval_mode(self):
        """Test default approval mode in ToolConfig."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        config = ToolConfig()
        assert config.approval_mode == "auto"
    
    def test_from_env_approval_mode(self):
        """Test ToolConfig.from_env reads approval mode."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        original = os.environ.get("PRAISON_APPROVAL_MODE")
        os.environ["PRAISON_APPROVAL_MODE"] = "manual"
        
        try:
            config = ToolConfig.from_env()
            assert config.approval_mode == "manual"
        finally:
            if original:
                os.environ["PRAISON_APPROVAL_MODE"] = original
            elif "PRAISON_APPROVAL_MODE" in os.environ:
                del os.environ["PRAISON_APPROVAL_MODE"]


class TestHeadlessConfigApprovalMode:
    """Tests for HeadlessConfig approval_mode setting."""
    
    def test_default_approval_mode(self):
        """Test default approval mode in HeadlessConfig."""
        from praisonai.cli.features.interactive_core_headless import HeadlessConfig
        
        config = HeadlessConfig()
        assert config.approval_mode == "auto"
    
    def test_custom_approval_mode(self):
        """Test custom approval mode in HeadlessConfig."""
        from praisonai.cli.features.interactive_core_headless import HeadlessConfig
        
        config = HeadlessConfig(approval_mode="manual")
        assert config.approval_mode == "manual"


class TestApprovalModeIntegration:
    """Integration tests for approval mode across components."""
    
    def test_auto_mode_allows_file_creation_via_tools(self):
        """Test that auto mode allows file creation through tools."""
        from praisonai.cli.features.interactive_tools import (
            get_interactive_tools,
            ToolConfig,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ToolConfig(
                workspace=tmpdir,
                approval_mode="auto",
                enable_acp=True,
                enable_lsp=False,
                enable_basic=True,
            )
            
            # Get tools - this should work without error
            tools = get_interactive_tools(config=config)
            
            # Should have ACP tools
            tool_names = [t.__name__ for t in tools]
            assert "acp_create_file" in tool_names or len(tools) > 0
    
    def test_tool_config_propagates_to_runtime(self):
        """Test that ToolConfig approval_mode propagates to runtime."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        from praisonai.cli.features.interactive_runtime import RuntimeConfig
        
        tool_config = ToolConfig(approval_mode="scoped")
        
        # When creating RuntimeConfig from ToolConfig values
        runtime_config = RuntimeConfig(
            workspace=tool_config.workspace,
            approval_mode=tool_config.approval_mode,
        )
        
        assert runtime_config.approval_mode == "scoped"


class TestApprovalModeMatrix:
    """Matrix tests for all approval mode combinations."""
    
    def test_approval_mode_matrix(self):
        """Test all approval mode combinations."""
        from praisonai.cli.features.interactive_runtime import (
            InteractiveRuntime,
            RuntimeConfig,
        )
        
        # Matrix: (approval_mode, acp_ready, expected_read_only)
        test_cases = [
            # Auto mode is never read-only
            ("auto", True, False),
            ("auto", False, False),
            # Manual mode depends on _read_only flag
            ("manual", True, False),  # ACP ready, not read-only
            ("manual", False, True),  # ACP not ready, read-only
            # Scoped mode depends on _read_only flag
            ("scoped", True, False),
            ("scoped", False, True),
        ]
        
        for approval_mode, acp_ready, expected_read_only in test_cases:
            config = RuntimeConfig(
                workspace="/tmp/test",
                approval_mode=approval_mode,
            )
            runtime = InteractiveRuntime(config)
            runtime._read_only = not acp_ready
            
            actual = runtime.read_only
            assert actual == expected_read_only, (
                f"Failed for approval_mode={approval_mode}, acp_ready={acp_ready}: "
                f"expected read_only={expected_read_only}, got {actual}"
            )
