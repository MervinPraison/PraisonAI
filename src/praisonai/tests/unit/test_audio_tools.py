"""
Unit tests for audio tools (TTS/STT).

Tests the wrapper-level audio tools that use the core AudioAgent.
"""

from unittest.mock import Mock, patch, MagicMock
import os
import tempfile


class TestTTSTool:
    """Test TTS tool functionality."""
    
    def test_tts_tool_success(self):
        """Test successful TTS conversion."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import tts_tool
            
            # Create a temp file to simulate output
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                temp_path = f.name
            
            # Mock speech to create the file
            def mock_speech(text, output, **kwargs):
                with open(output, 'w') as f:
                    f.write('fake audio')
            
            mock_agent.speech.side_effect = mock_speech
            
            result = tts_tool("Hello world", output_dir=os.path.dirname(temp_path))
            
            assert result["success"] is True
            assert "audio_path" in result
            assert result["media_line"].startswith("MEDIA:")
            
            # Cleanup
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_tts_tool_with_voice(self):
        """Test TTS with custom voice."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import tts_tool
            
            # Mock speech to create a file
            def mock_speech(text, output, **kwargs):
                with open(output, 'w') as f:
                    f.write('fake audio')
            
            mock_agent.speech.side_effect = mock_speech
            
            result = tts_tool("Hello", voice="echo")
            
            # Verify voice was passed
            mock_agent.speech.assert_called_once()
            call_kwargs = mock_agent.speech.call_args[1]
            assert call_kwargs.get("voice") == "echo"
    
    def test_tts_tool_error_handling(self):
        """Test TTS error handling."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_agent.speech.side_effect = Exception("API error")
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import tts_tool
            
            result = tts_tool("Hello world")
            
            assert result["success"] is False
            assert "error" in result
            assert "API error" in result["error"]
    
    def test_tts_tool_opus_voice_compatible(self):
        """Test that opus format is marked as voice compatible."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import tts_tool
            
            def mock_speech(text, output, **kwargs):
                with open(output, 'w') as f:
                    f.write('fake audio')
            
            mock_agent.speech.side_effect = mock_speech
            
            result = tts_tool("Hello", output_format="opus")
            
            assert result["success"] is True
            assert result["voice_compatible"] is True


class TestSTTTool:
    """Test STT tool functionality."""
    
    def test_stt_tool_success(self):
        """Test successful STT transcription."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_agent.transcribe.return_value = "Hello world"
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import stt_tool
            
            # Create a temp audio file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(b'fake audio data')
                temp_path = f.name
            
            try:
                result = stt_tool(temp_path)
                
                assert result["success"] is True
                assert result["text"] == "Hello world"
            finally:
                os.unlink(temp_path)
    
    def test_stt_tool_file_not_found(self):
        """Test STT with non-existent file."""
        from praisonai.tools.audio import stt_tool
        
        result = stt_tool("/nonexistent/path/audio.mp3")
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    def test_stt_tool_with_language(self):
        """Test STT with language parameter."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_agent.transcribe.return_value = "Hola mundo"
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import stt_tool
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(b'fake audio')
                temp_path = f.name
            
            try:
                result = stt_tool(temp_path, language="es")
                
                # Verify language was passed
                mock_agent.transcribe.assert_called_once()
                call_kwargs = mock_agent.transcribe.call_args[1]
                assert call_kwargs.get("language") == "es"
            finally:
                os.unlink(temp_path)
    
    def test_stt_tool_error_handling(self):
        """Test STT error handling."""
        with patch('praisonai.tools.audio._get_audio_agent') as mock_get_agent:
            mock_agent = Mock()
            mock_agent.transcribe.side_effect = Exception("Transcription failed")
            mock_get_agent.return_value = mock_agent
            
            from praisonai.tools.audio import stt_tool
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(b'fake audio')
                temp_path = f.name
            
            try:
                result = stt_tool(temp_path)
                
                assert result["success"] is False
                assert "Transcription failed" in result["error"]
            finally:
                os.unlink(temp_path)


class TestCreateToolFunctions:
    """Test the create_*_tool factory functions."""
    
    def test_create_tts_tool(self):
        """Test create_tts_tool returns a callable."""
        with patch('praisonai.tools.audio._get_audio_agent'):
            from praisonai.tools.audio import create_tts_tool
            
            tool = create_tts_tool()
            
            assert callable(tool)
            assert hasattr(tool, '__name__') or hasattr(tool, 'name')
    
    def test_create_stt_tool(self):
        """Test create_stt_tool returns a callable."""
        with patch('praisonai.tools.audio._get_audio_agent'):
            from praisonai.tools.audio import create_stt_tool
            
            tool = create_stt_tool()
            
            assert callable(tool)
            assert hasattr(tool, '__name__') or hasattr(tool, 'name')


class TestBotCapabilitiesTTS:
    """Test TTS/STT in BotCapabilities."""
    
    def test_bot_capabilities_tts_fields(self):
        """Test BotCapabilities has TTS/STT fields."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(
            tts=True,
            tts_voice="echo",
            tts_model="openai/tts-1-hd",
            auto_tts=True,
            stt=True,
            stt_model="openai/whisper-1",
        )
        
        assert caps.tts is True
        assert caps.tts_voice == "echo"
        assert caps.tts_model == "openai/tts-1-hd"
        assert caps.auto_tts is True
        assert caps.stt is True
        assert caps.stt_model == "openai/whisper-1"
    
    def test_bot_capabilities_to_dict_includes_tts(self):
        """Test to_dict includes TTS/STT fields."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(tts=True, stt=True)
        d = caps.to_dict()
        
        assert "tts" in d
        assert "stt" in d
        assert "auto_tts" in d
        assert d["tts"] is True
        assert d["stt"] is True
    
    def test_build_capabilities_from_args_tts(self):
        """Test _build_capabilities_from_args includes TTS/STT."""
        from praisonai.cli.features.bots_cli import _build_capabilities_from_args
        from argparse import Namespace
        
        args = Namespace(
            browser=False,
            browser_profile="default",
            browser_headless=False,
            tools=[],
            skills=[],
            skills_dir=None,
            memory=False,
            memory_provider="default",
            knowledge=False,
            knowledge_sources=[],
            web_search=False,
            web_provider="duckduckgo",
            sandbox=False,
            exec_enabled=False,
            auto_approve=False,
            model=None,
            thinking=None,
            tts=True,
            tts_voice="nova",
            tts_model="openai/tts-1-hd",
            auto_tts=True,
            stt=True,
            stt_model="openai/whisper-1",
            session_id=None,
            user_id=None,
        )
        
        caps = _build_capabilities_from_args(args)
        
        assert caps.tts is True
        assert caps.tts_voice == "nova"
        assert caps.tts_model == "openai/tts-1-hd"
        assert caps.auto_tts is True
        assert caps.stt is True
        assert caps.stt_model == "openai/whisper-1"
