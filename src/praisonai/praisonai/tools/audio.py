"""
Audio Tools for PraisonAI Bots.

Provides TTS and STT tools that wrap the core AudioAgent for use by agents.
These tools enable agents to convert text to speech and transcribe audio.

Following moltbot patterns:
- tts_tool: Convert text to speech, return audio file path
- stt_tool: Transcribe audio file to text
"""

from __future__ import annotations

import os
import tempfile
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Lazy-loaded AudioAgent instance (shared for efficiency)
_audio_agent = None


def _get_audio_agent():
    """Lazy load AudioAgent from core SDK."""
    global _audio_agent
    if _audio_agent is None:
        try:
            from praisonaiagents import AudioAgent
            _audio_agent = AudioAgent(verbose=False)
        except ImportError:
            raise ImportError(
                "AudioAgent requires litellm. "
                "Install with: pip install praisonaiagents[llm]"
            )
    return _audio_agent


def tts_tool(
    text: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "mp3",
) -> Dict[str, Any]:
    """
    Convert text to speech and return the audio file path.
    
    This tool wraps the core AudioAgent.speech() method for use by agents.
    Similar to moltbot's tts-tool, it returns a MEDIA: path that can be
    sent to messaging platforms.
    
    Args:
        text: Text to convert to speech
        voice: Voice to use (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")
        model: TTS model (default: "openai/tts-1")
        output_dir: Directory to save audio (default: temp directory)
        output_format: Audio format (mp3, opus, aac, flac, wav)
        
    Returns:
        Dict with:
            - success: bool
            - audio_path: str (path to audio file)
            - media_line: str (MEDIA:path for bot responses)
            - error: str (if failed)
            
    Example:
        result = tts_tool("Hello world!")
        if result["success"]:
            print(result["media_line"])  # MEDIA:/tmp/tts_abc123.mp3
    """
    try:
        agent = _get_audio_agent()
        
        # Determine output path
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"tts_{os.urandom(8).hex()}.{output_format}")
        else:
            # Use temp directory
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"tts_{os.urandom(8).hex()}.{output_format}"
            )
        
        # Build kwargs
        kwargs = {"response_format": output_format}
        if voice:
            kwargs["voice"] = voice
        if model:
            kwargs["model"] = model
        
        # Generate speech
        agent.speech(text, output=output_path, **kwargs)
        
        # Check if file was created
        if os.path.exists(output_path):
            # Determine if voice-compatible (opus for Telegram)
            voice_compatible = output_format.lower() in ("opus", "ogg")
            
            return {
                "success": True,
                "audio_path": output_path,
                "media_line": f"MEDIA:{output_path}",
                "voice_compatible": voice_compatible,
                "format": output_format,
            }
        else:
            return {
                "success": False,
                "error": "Audio file was not created",
            }
            
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def stt_tool(
    audio_path: str,
    language: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transcribe audio file to text.
    
    This tool wraps the core AudioAgent.transcribe() method for use by agents.
    
    Args:
        audio_path: Path to audio file to transcribe
        language: Language code (e.g., "en", "es", "fr")
        model: STT model (default: "openai/whisper-1")
        
    Returns:
        Dict with:
            - success: bool
            - text: str (transcribed text)
            - error: str (if failed)
            
    Example:
        result = stt_tool("audio.mp3")
        if result["success"]:
            print(result["text"])
    """
    try:
        if not os.path.exists(audio_path):
            return {
                "success": False,
                "error": f"Audio file not found: {audio_path}",
            }
        
        agent = _get_audio_agent()
        
        # Build kwargs
        kwargs = {}
        if language:
            kwargs["language"] = language
        if model:
            kwargs["model"] = model
        
        # Transcribe
        text = agent.transcribe(audio_path, **kwargs)
        
        return {
            "success": True,
            "text": text,
        }
        
    except Exception as e:
        logger.error(f"STT error: {e}")
        return {
            "success": False,
            "error": str(e),
        }


# Tool functions decorated for agent use
def create_tts_tool():
    """
    Create a TTS tool function for use with agents.
    
    Returns a function that can be added to an agent's tools list.
    
    Example:
        from praisonai.tools.audio import create_tts_tool
        from praisonaiagents import Agent
        
        agent = Agent(
            name="assistant",
            tools=[create_tts_tool()]
        )
    """
    try:
        from praisonaiagents import tool
    except ImportError:
        raise ImportError("praisonaiagents is required")
    
    @tool
    def tts(text: str, voice: str = "alloy") -> str:
        """
        Convert text to speech and return the audio file path.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            
        Returns:
            MEDIA: path to the generated audio file, or error message
        """
        result = tts_tool(text, voice=voice)
        if result["success"]:
            return result["media_line"]
        return f"Error: {result['error']}"
    
    return tts


def create_stt_tool():
    """
    Create an STT tool function for use with agents.
    
    Returns a function that can be added to an agent's tools list.
    
    Example:
        from praisonai.tools.audio import create_stt_tool
        from praisonaiagents import Agent
        
        agent = Agent(
            name="assistant",
            tools=[create_stt_tool()]
        )
    """
    try:
        from praisonaiagents import tool
    except ImportError:
        raise ImportError("praisonaiagents is required")
    
    @tool
    def stt(audio_path: str, language: str = None) -> str:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to audio file to transcribe
            language: Optional language code (en, es, fr, etc.)
            
        Returns:
            Transcribed text, or error message
        """
        result = stt_tool(audio_path, language=language)
        if result["success"]:
            return result["text"]
        return f"Error: {result['error']}"
    
    return stt


# Convenience exports
__all__ = [
    "tts_tool",
    "stt_tool",
    "create_tts_tool",
    "create_stt_tool",
]
