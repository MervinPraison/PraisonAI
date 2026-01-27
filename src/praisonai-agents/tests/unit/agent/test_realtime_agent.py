"""Tests for RealtimeAgent - Real-time voice conversations."""

import unittest
from unittest.mock import Mock, MagicMock, AsyncMock


class TestRealtimeAgentInit(unittest.TestCase):
    """Test RealtimeAgent initialization."""
    
    def test_import_realtime_agent(self):
        """RealtimeAgent should be importable from praisonaiagents."""
        from praisonaiagents import RealtimeAgent
        assert RealtimeAgent is not None
    
    def test_import_realtime_config(self):
        """RealtimeConfig should be importable."""
        from praisonaiagents.agent.realtime_agent import RealtimeConfig
        assert RealtimeConfig is not None
    
    def test_default_initialization(self):
        """RealtimeAgent should initialize with defaults."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent()
        assert agent is not None
        assert agent.name == "RealtimeAgent"
    
    def test_custom_name(self):
        """RealtimeAgent should accept custom name."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(name="MyRealtime")
        assert agent.name == "MyRealtime"
    
    def test_custom_model(self):
        """RealtimeAgent should accept custom model."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(llm="gpt-4o-realtime-preview")
        assert agent.llm == "gpt-4o-realtime-preview"
    
    def test_default_model(self):
        """RealtimeAgent should have appropriate default model."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent()
        assert "realtime" in agent.llm.lower() or "gpt-4o" in agent.llm.lower()


class TestRealtimeConfig(unittest.TestCase):
    """Test RealtimeConfig dataclass."""
    
    def test_default_config(self):
        """RealtimeConfig should have sensible defaults."""
        from praisonaiagents.agent.realtime_agent import RealtimeConfig
        config = RealtimeConfig()
        assert config.voice is not None
        assert config.modalities is not None
    
    def test_custom_config(self):
        """RealtimeConfig should accept custom values."""
        from praisonaiagents.agent.realtime_agent import RealtimeConfig
        config = RealtimeConfig(
            voice="shimmer",
            modalities=["text", "audio"],
            turn_detection="server_vad"
        )
        assert config.voice == "shimmer"
        assert "audio" in config.modalities
    
    def test_config_to_dict(self):
        """RealtimeConfig should convert to dict."""
        from praisonaiagents.agent.realtime_agent import RealtimeConfig
        config = RealtimeConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "voice" in d


class TestRealtimeAgentConnect(unittest.TestCase):
    """Test RealtimeAgent.connect() method."""
    
    def test_connect_method_exists(self):
        """connect() method should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'connect')
        assert callable(agent.connect)
    
    def test_disconnect_method_exists(self):
        """disconnect() method should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'disconnect')
        assert callable(agent.disconnect)


class TestRealtimeAgentSend(unittest.TestCase):
    """Test RealtimeAgent.send() method."""
    
    def test_send_text_method_exists(self):
        """send_text() method should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'send_text')
        assert callable(agent.send_text)
    
    def test_send_audio_method_exists(self):
        """send_audio() method should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'send_audio')
        assert callable(agent.send_audio)


class TestRealtimeAgentReceive(unittest.TestCase):
    """Test RealtimeAgent receive methods."""
    
    def test_on_message_method_exists(self):
        """on_message() callback registration should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'on_message')
    
    def test_on_audio_method_exists(self):
        """on_audio() callback registration should exist."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'on_audio')


class TestRealtimeAgentAsync(unittest.TestCase):
    """Test async methods of RealtimeAgent."""
    
    def test_aconnect_exists(self):
        """aconnect() should exist as async method."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'aconnect')
        assert callable(agent.aconnect)
    
    def test_adisconnect_exists(self):
        """adisconnect() should exist as async method."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(verbose=False)
        assert hasattr(agent, 'adisconnect')
        assert callable(agent.adisconnect)


class TestRealtimeAgentLazyLoading(unittest.TestCase):
    """Test lazy loading behavior."""
    
    def test_client_not_created_at_init(self):
        """WebSocket client should not be created until needed."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent()
        assert agent._client is None
    
    def test_console_lazy_loaded(self):
        """Rich console should be lazy loaded."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent()
        assert agent._console is None


class TestRealtimeAgentConfigResolution(unittest.TestCase):
    """Test configuration resolution (Precedence Ladder)."""
    
    def test_bool_config(self):
        """realtime=True should use defaults."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(realtime=True)
        assert agent._realtime_config is not None
    
    def test_dict_config(self):
        """realtime=dict should create RealtimeConfig."""
        from praisonaiagents import RealtimeAgent
        agent = RealtimeAgent(realtime={"voice": "echo"})
        assert agent._realtime_config.voice == "echo"
    
    def test_config_instance(self):
        """realtime=RealtimeConfig should use directly."""
        from praisonaiagents.agent.realtime_agent import RealtimeConfig
        from praisonaiagents import RealtimeAgent
        config = RealtimeConfig(voice="fable")
        agent = RealtimeAgent(realtime=config)
        assert agent._realtime_config.voice == "fable"


if __name__ == "__main__":
    unittest.main()
