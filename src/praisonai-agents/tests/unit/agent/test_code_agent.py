"""Tests for CodeAgent - Code generation and execution with sandboxing."""

import unittest


class TestCodeAgentInit(unittest.TestCase):
    """Test CodeAgent initialization."""
    
    def test_import_code_agent(self):
        """CodeAgent should be importable from praisonaiagents."""
        from praisonaiagents import CodeAgent
        assert CodeAgent is not None
    
    def test_import_code_config(self):
        """CodeConfig should be importable."""
        from praisonaiagents.agent.code_agent import CodeConfig
        assert CodeConfig is not None
    
    def test_default_initialization(self):
        """CodeAgent should initialize with defaults."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent()
        assert agent is not None
        assert agent.name == "CodeAgent"
    
    def test_custom_name(self):
        """CodeAgent should accept custom name."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(name="MyCodeAgent")
        assert agent.name == "MyCodeAgent"
    
    def test_custom_model(self):
        """CodeAgent should accept custom model."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(llm="gpt-4o")
        assert agent.llm == "gpt-4o"
    
    def test_default_model(self):
        """CodeAgent should have appropriate default model."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent()
        assert agent.llm is not None


class TestCodeConfig(unittest.TestCase):
    """Test CodeConfig dataclass."""
    
    def test_default_config(self):
        """CodeConfig should have sensible defaults."""
        from praisonaiagents.agent.code_agent import CodeConfig
        config = CodeConfig()
        assert config.sandbox is not None
        assert config.timeout > 0
    
    def test_custom_config(self):
        """CodeConfig should accept custom values."""
        from praisonaiagents.agent.code_agent import CodeConfig
        config = CodeConfig(
            sandbox=True,
            timeout=60,
            allowed_languages=["python", "javascript"]
        )
        assert config.sandbox is True
        assert config.timeout == 60
        assert "python" in config.allowed_languages
    
    def test_config_to_dict(self):
        """CodeConfig should convert to dict."""
        from praisonaiagents.agent.code_agent import CodeConfig
        config = CodeConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "sandbox" in d


class TestCodeAgentGenerate(unittest.TestCase):
    """Test CodeAgent.generate() method."""
    
    def test_generate_method_exists(self):
        """generate() method should exist."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'generate')
        assert callable(agent.generate)
    
    def test_generate_code_method_exists(self):
        """generate_code() method should exist."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'generate_code')
        assert callable(agent.generate_code)


class TestCodeAgentExecute(unittest.TestCase):
    """Test CodeAgent.execute() method."""
    
    def test_execute_method_exists(self):
        """execute() method should exist."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'execute')
        assert callable(agent.execute)
    
    def test_execute_code_method_exists(self):
        """execute_code() method should exist."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'execute_code')
        assert callable(agent.execute_code)


class TestCodeAgentReview(unittest.TestCase):
    """Test CodeAgent.review() method."""
    
    def test_review_method_exists(self):
        """review() method should exist for code review."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'review')
        assert callable(agent.review)
    
    def test_explain_method_exists(self):
        """explain() method should exist for code explanation."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'explain')
        assert callable(agent.explain)


class TestCodeAgentRefactor(unittest.TestCase):
    """Test CodeAgent.refactor() method."""
    
    def test_refactor_method_exists(self):
        """refactor() method should exist."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'refactor')
        assert callable(agent.refactor)
    
    def test_fix_method_exists(self):
        """fix() method should exist for bug fixing."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'fix')
        assert callable(agent.fix)


class TestCodeAgentAsync(unittest.TestCase):
    """Test async methods of CodeAgent."""
    
    def test_agenerate_exists(self):
        """agenerate() should exist as async method."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'agenerate')
        assert callable(agent.agenerate)
    
    def test_aexecute_exists(self):
        """aexecute() should exist as async method."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(verbose=False)
        assert hasattr(agent, 'aexecute')
        assert callable(agent.aexecute)


class TestCodeAgentLazyLoading(unittest.TestCase):
    """Test lazy loading behavior."""
    
    def test_litellm_not_imported_at_init(self):
        """litellm should not be imported until needed."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent()
        assert agent._litellm is None
    
    def test_console_lazy_loaded(self):
        """Rich console should be lazy loaded."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent()
        assert agent._console is None


class TestCodeAgentConfigResolution(unittest.TestCase):
    """Test configuration resolution (Precedence Ladder)."""
    
    def test_bool_config(self):
        """code=True should use defaults."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(code=True)
        assert agent._code_config is not None
    
    def test_dict_config(self):
        """code=dict should create CodeConfig."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(code={"timeout": 120})
        assert agent._code_config.timeout == 120
    
    def test_config_instance(self):
        """code=CodeConfig should use directly."""
        from praisonaiagents.agent.code_agent import CodeConfig
        from praisonaiagents import CodeAgent
        config = CodeConfig(sandbox=False)
        agent = CodeAgent(code=config)
        assert agent._code_config.sandbox is False


class TestCodeAgentSandbox(unittest.TestCase):
    """Test sandbox functionality."""
    
    def test_sandbox_enabled_by_default(self):
        """Sandbox should be enabled by default for safety."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent()
        assert agent._code_config.sandbox is True
    
    def test_sandbox_can_be_disabled(self):
        """Sandbox can be disabled explicitly."""
        from praisonaiagents import CodeAgent
        agent = CodeAgent(code={"sandbox": False})
        assert agent._code_config.sandbox is False


if __name__ == "__main__":
    unittest.main()
