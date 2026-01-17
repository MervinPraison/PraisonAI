"""
Unit tests for AudioAgent class.
Tests TTS (speech) and STT (transcribe) operations with mocked LiteLLM.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Mock Objects
# ─────────────────────────────────────────────────────────────────────────────

class MockSpeechResponse:
    """Mock speech response with stream_to_file method."""
    def __init__(self, content=b"audio_bytes"):
        self.content = content
    
    def stream_to_file(self, path):
        with open(path, "wb") as f:
            f.write(self.content)


class MockTranscriptionResponse:
    """Mock transcription response."""
    def __init__(self, text="Hello, this is transcribed text."):
        self.text = text


# ─────────────────────────────────────────────────────────────────────────────
# Import Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAgentImport:
    """Test that AudioAgent can be imported correctly."""
    
    def test_import_from_praisonaiagents(self):
        """Test import from main package."""
        from praisonaiagents import AudioAgent, AudioConfig
        assert AudioAgent is not None
        assert AudioConfig is not None
    
    def test_import_from_agent_module(self):
        """Test import from agent submodule."""
        from praisonaiagents.agent import AudioAgent, AudioConfig
        assert AudioAgent is not None
        assert AudioConfig is not None
    
    def test_import_direct(self):
        """Test direct import from audio_agent module."""
        from praisonaiagents.agent.audio_agent import AudioAgent, AudioConfig
        assert AudioAgent is not None
        assert AudioConfig is not None


# ─────────────────────────────────────────────────────────────────────────────
# Initialization Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAgentInit:
    """Test AudioAgent initialization."""
    
    def test_default_initialization(self):
        """Test default initialization."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent()
        assert agent.name == "AudioAgent"
        assert agent.llm is None  # No default - uses method-specific defaults
        assert agent.verbose == True
    
    def test_with_tts_model(self):
        """Test initialization with TTS model."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/tts-1")
        assert agent.llm == "openai/tts-1"
    
    def test_with_stt_model(self):
        """Test initialization with STT model."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/whisper-1")
        assert agent.llm == "openai/whisper-1"
    
    def test_model_alias(self):
        """Test model= alias for llm=."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(model="elevenlabs/eleven_multilingual_v2")
        assert agent.llm == "elevenlabs/eleven_multilingual_v2"
    
    def test_with_name(self):
        """Test initialization with custom name."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(name="MyVoiceAgent")
        assert agent.name == "MyVoiceAgent"


# ─────────────────────────────────────────────────────────────────────────────
# AudioConfig Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioConfig:
    """Test AudioConfig dataclass."""
    
    def test_default_values(self):
        """Test default AudioConfig values."""
        from praisonaiagents import AudioConfig
        
        config = AudioConfig()
        assert config.voice == "alloy"
        assert config.speed == 1.0
        assert config.response_format == "mp3"
        assert config.language is None
        assert config.temperature == 0.0
        assert config.timeout == 600
    
    def test_custom_values(self):
        """Test AudioConfig with custom values."""
        from praisonaiagents import AudioConfig
        
        config = AudioConfig(
            voice="nova",
            speed=1.5,
            response_format="wav",
            language="en"
        )
        assert config.voice == "nova"
        assert config.speed == 1.5
        assert config.response_format == "wav"
        assert config.language == "en"
    
    def test_to_dict(self):
        """Test AudioConfig.to_dict() method."""
        from praisonaiagents import AudioConfig
        
        config = AudioConfig(voice="echo", speed=0.8)
        d = config.to_dict()
        
        assert d["voice"] == "echo"
        assert d["speed"] == 0.8


class TestAudioConfigPrecedenceLadder:
    """Test Precedence Ladder for audio configuration."""
    
    def test_bool_true_uses_defaults(self):
        """Test audio=True uses default config."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(audio=True)
        assert agent._audio_config.voice == "alloy"
    
    def test_dict_configuration(self):
        """Test audio=dict configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(audio={"voice": "nova", "speed": 1.2})
        assert agent._audio_config.voice == "nova"
        assert agent._audio_config.speed == 1.2
    
    def test_config_instance(self):
        """Test audio=AudioConfig() instance."""
        from praisonaiagents import AudioAgent, AudioConfig
        
        config = AudioConfig(voice="shimmer", speed=0.9)
        agent = AudioAgent(audio=config)
        assert agent._audio_config.voice == "shimmer"
        assert agent._audio_config.speed == 0.9


# ─────────────────────────────────────────────────────────────────────────────
# TTS Operation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAgentTTS:
    """Test Text-to-Speech operations with mocked LiteLLM."""
    
    @pytest.fixture
    def tts_agent(self):
        """Create AudioAgent with mocked litellm for TTS."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/tts-1", verbose=False)
        
        # Mock litellm
        mock_litellm = MagicMock()
        mock_litellm.speech = Mock(return_value=MockSpeechResponse())
        mock_litellm.aspeech = Mock(return_value=MockSpeechResponse())
        agent._litellm = mock_litellm
        
        return agent
    
    def test_speech_basic(self, tts_agent):
        """Test basic speech generation."""
        response = tts_agent.speech("Hello world")
        
        assert response is not None
        tts_agent._litellm.speech.assert_called_once()
    
    def test_speech_with_output(self, tts_agent, tmp_path):
        """Test speech with file output."""
        output_path = str(tmp_path / "test.mp3")
        response = tts_agent.speech("Hello world", output=output_path)
        
        assert response is not None
        tts_agent._litellm.speech.assert_called_once()
    
    def test_speech_with_voice(self, tts_agent):
        """Test speech with custom voice."""
        tts_agent.speech("Hello", voice="nova")
        
        call_kwargs = tts_agent._litellm.speech.call_args.kwargs
        assert call_kwargs["voice"] == "nova"
    
    def test_say_convenience(self, tts_agent, tmp_path):
        """Test say() convenience method."""
        output_path = str(tmp_path / "say.mp3")
        result = tts_agent.say("Quick test", output=output_path)
        
        assert result == output_path
        tts_agent._litellm.speech.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# STT Operation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAgentSTT:
    """Test Speech-to-Text operations with mocked LiteLLM."""
    
    @pytest.fixture
    def stt_agent(self):
        """Create AudioAgent with mocked litellm for STT."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/whisper-1", verbose=False)
        
        # Mock litellm
        mock_litellm = MagicMock()
        mock_litellm.transcription = Mock(return_value=MockTranscriptionResponse())
        mock_litellm.atranscription = Mock(return_value=MockTranscriptionResponse())
        agent._litellm = mock_litellm
        
        return agent
    
    def test_transcribe_with_file_object(self, stt_agent, tmp_path):
        """Test transcription with file object."""
        # Create a dummy audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")
        
        with open(audio_file, "rb") as f:
            text = stt_agent.transcribe(f)
        
        assert text == "Hello, this is transcribed text."
        stt_agent._litellm.transcription.assert_called_once()
    
    def test_transcribe_with_language(self, stt_agent, tmp_path):
        """Test transcription with language parameter."""
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")
        
        with open(audio_file, "rb") as f:
            stt_agent.transcribe(f, language="en")
        
        call_kwargs = stt_agent._litellm.transcription.call_args.kwargs
        assert call_kwargs["language"] == "en"
    
    def test_listen_convenience(self, stt_agent, tmp_path):
        """Test listen() convenience method."""
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")
        
        with open(audio_file, "rb") as f:
            text = stt_agent.listen(f)
        
        assert text == "Hello, this is transcribed text."


# ─────────────────────────────────────────────────────────────────────────────
# Provider Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAgentProviders:
    """Test provider-specific configurations."""
    
    def test_openai_tts(self):
        """Test OpenAI TTS configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/tts-1")
        assert "openai" in agent.llm
    
    def test_openai_tts_hd(self):
        """Test OpenAI TTS-HD configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/tts-1-hd")
        assert "tts-1-hd" in agent.llm
    
    def test_openai_whisper(self):
        """Test OpenAI Whisper configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="openai/whisper-1")
        assert "whisper" in agent.llm
    
    def test_elevenlabs(self):
        """Test ElevenLabs configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="elevenlabs/eleven_multilingual_v2")
        assert "elevenlabs" in agent.llm
    
    def test_groq_whisper(self):
        """Test Groq Whisper configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="groq/whisper-large-v3")
        assert "groq" in agent.llm
    
    def test_deepgram(self):
        """Test Deepgram configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="deepgram/nova-2")
        assert "deepgram" in agent.llm
    
    def test_gemini_tts(self):
        """Test Gemini TTS configuration."""
        from praisonaiagents import AudioAgent
        
        agent = AudioAgent(llm="gemini/gemini-2.5-flash-preview-tts")
        assert "gemini" in agent.llm


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
