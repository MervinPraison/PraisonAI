"""
AudioAgent - A specialized agent class for audio processing using AI models.
Provides Text-to-Speech (TTS) and Speech-to-Text (STT/Transcription) capabilities.

Follows the Agent() class patterns:
- Precedence Ladder: Instance > Config > Array > Dict > String > Bool > Default
- Lazy imports for LiteLLM (zero overhead until first use)
- Async-safe with both sync and async methods
"""
import os
import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, Union, BinaryIO
from pathlib import Path

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)


# ─────────────────────────────────────────────────────────────────────────────
# AudioConfig - Configuration dataclass following feature_configs.py patterns
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AudioConfig:
    """
    Configuration for audio processing settings.
    
    Follows the Precedence Ladder pattern:
    - Instance > Config > Array > Dict > String > Bool > Default
    """
    # TTS settings
    voice: Optional[str] = "alloy"
    speed: float = 1.0
    response_format: str = "mp3"  # mp3, opus, aac, flac, wav, pcm
    
    # STT settings
    language: Optional[str] = None
    temperature: float = 0.0
    
    # Common settings
    timeout: int = 600
    
    # API configuration
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LiteLLM calls."""
        return {
            "voice": self.voice,
            "speed": self.speed,
            "response_format": self.response_format,
            "language": self.language,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "api_base": self.api_base,
            "api_key": self.api_key,
        }


# ─────────────────────────────────────────────────────────────────────────────
# AudioAgent Class - Agent-centric audio processing
# ─────────────────────────────────────────────────────────────────────────────

class AudioAgent:
    """
    A specialized agent for audio processing using AI models.
    
    Provides:
    - Text-to-Speech (TTS): Convert text to spoken audio
    - Speech-to-Text (STT): Transcribe audio to text
    
    TTS Providers:
        - OpenAI: `openai/tts-1`, `openai/tts-1-hd`
        - Azure: `azure/tts-1`
        - Gemini: `gemini/gemini-2.5-flash-preview-tts`
        - Vertex AI: `vertex_ai/gemini-2.5-flash-preview-tts`
        - ElevenLabs: `elevenlabs/eleven_multilingual_v2`
        - MiniMax: `minimax/speech-01`
    
    STT Providers:
        - OpenAI: `openai/whisper-1`
        - Azure: `azure/whisper`
        - Groq: `groq/whisper-large-v3`
        - Deepgram: `deepgram/nova-2`
        - Gemini: `gemini/gemini-2.0-flash`
    
    Example:
        ```python
        from praisonaiagents import AudioAgent
        
        # Text-to-Speech
        agent = AudioAgent(llm="openai/tts-1")
        agent.speech("Hello world!", output="hello.mp3")
        
        # Speech-to-Text
        agent = AudioAgent(llm="openai/whisper-1")
        text = agent.transcribe("audio.mp3")
        print(text)
        ```
    """
    
    # Default models
    DEFAULT_TTS_MODEL = "openai/tts-1"
    DEFAULT_STT_MODEL = "openai/whisper-1"
    
    def __init__(
        self,
        # Core identity
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        # LLM configuration
        llm: Optional[str] = None,
        model: Optional[str] = None,  # Alias for llm=
        # Connection/auth
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        # Audio-specific configuration
        audio: Optional[Union[bool, Dict, "AudioConfig"]] = None,
        # Output configuration
        verbose: Union[bool, int] = True,
    ):
        """Initialize AudioAgent.
        
        Args:
            name: Agent name for identification
            instructions: Optional instructions
            llm: Model name (e.g., "openai/tts-1", "openai/whisper-1")
            model: Alias for llm= parameter
            base_url: Custom API endpoint URL
            api_key: API key for the provider
            audio: Audio configuration. Accepts:
                - bool: True enables with defaults
                - dict: {"voice": "alloy", "speed": 1.0}
                - AudioConfig: Full configuration object
            verbose: Verbosity level for output
        """
        # Handle model= alias
        if llm is None and model is not None:
            llm = model
        
        self.name = name or "AudioAgent"
        self.instructions = instructions
        self.llm = llm  # Can be None - will use defaults based on method
        self.base_url = base_url
        self.api_key = api_key
        self._audio_config = self._resolve_audio_config(audio)
        self.verbose = verbose
        
        # Lazy load LiteLLM
        self._litellm = None
        self._console = None
        
        self._configure_logging(verbose)
    
    def _resolve_audio_config(self, audio: Optional[Union[bool, Dict, AudioConfig]]) -> AudioConfig:
        """Resolve audio parameter using Precedence Ladder."""
        if audio is None or audio is True or audio is False:
            return AudioConfig()
        elif isinstance(audio, AudioConfig):
            return audio
        elif isinstance(audio, dict):
            return AudioConfig(**audio)
        return AudioConfig()
    
    @property
    def console(self):
        """Lazily initialize Rich Console."""
        if self._console is None:
            from rich.console import Console
            self._console = Console()
        return self._console
    
    @property
    def litellm(self):
        """Lazy load litellm module when needed."""
        if self._litellm is None:
            try:
                import litellm
                litellm.telemetry = False
                litellm.success_callback = []
                self._litellm = litellm
            except ImportError:
                raise ImportError(
                    "litellm is required for audio processing. "
                    "Please install with: pip install litellm"
                )
        return self._litellm
    
    def _configure_logging(self, verbose: Union[bool, int]) -> None:
        """Configure logging levels."""
        if isinstance(verbose, int) and verbose >= 10:
            logging.getLogger("litellm").setLevel(logging.DEBUG)
        else:
            logging.getLogger("litellm").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
    
    def _get_model_params(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Build parameters for LiteLLM calls."""
        params = {"model": model or self.llm}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["api_base"] = self.base_url
        return params
    
    # ─────────────────────────────────────────────────────────────────────────
    # Text-to-Speech (TTS)
    # ─────────────────────────────────────────────────────────────────────────
    
    def speech(
        self,
        text: str,
        output: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Convert text to speech.
        
        Args:
            text: Text to convert to speech
            output: Path to save audio file (optional)
            voice: Voice to use (e.g., "alloy", "echo", "fable")
            speed: Speech speed (0.25 to 4.0)
            response_format: Audio format (mp3, opus, aac, flac, wav)
            model: Override model for this call
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Audio response object with stream_to_file() method
            
        Example:
            ```python
            agent = AudioAgent(llm="openai/tts-1")
            agent.speech("Hello world!", output="hello.mp3")
            ```
        """
        # Resolve model
        model = model or self.llm or self.DEFAULT_TTS_MODEL
        
        # Build params
        params = self._get_model_params(model)
        params["input"] = text
        params["voice"] = voice or self._audio_config.voice
        
        if speed is not None:
            params["speed"] = speed
        elif self._audio_config.speed != 1.0:
            params["speed"] = self._audio_config.speed
            
        if response_format:
            params["response_format"] = response_format
        elif self._audio_config.response_format != "mp3":
            params["response_format"] = self._audio_config.response_format
        
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Generating speech with {model}...[/cyan]")
        
        response = self.litellm.speech(**params)
        
        if output:
            response.stream_to_file(Path(output))
            if self.verbose:
                self.console.print(f"[green]✓ Audio saved to {output}[/green]")
        
        return response
    
    async def aspeech(
        self,
        text: str,
        output: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Async version of speech()."""
        model = model or self.llm or self.DEFAULT_TTS_MODEL
        
        params = self._get_model_params(model)
        params["input"] = text
        params["voice"] = voice or self._audio_config.voice
        
        if speed is not None:
            params["speed"] = speed
        elif self._audio_config.speed != 1.0:
            params["speed"] = self._audio_config.speed
            
        if response_format:
            params["response_format"] = response_format
        
        params.update(kwargs)
        
        response = await self.litellm.aspeech(**params)
        
        if output:
            response.stream_to_file(Path(output))
        
        return response
    
    # ─────────────────────────────────────────────────────────────────────────
    # Speech-to-Text (STT / Transcription)
    # ─────────────────────────────────────────────────────────────────────────
    
    def transcribe(
        self,
        file: Union[str, BinaryIO],
        language: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Transcribe audio to text.
        
        Args:
            file: Path to audio file or file-like object
            language: Language code (e.g., "en", "es", "fr")
            temperature: Sampling temperature (0.0 to 1.0)
            model: Override model for this call
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Transcribed text
            
        Example:
            ```python
            agent = AudioAgent(llm="openai/whisper-1")
            text = agent.transcribe("audio.mp3")
            print(text)
            ```
        """
        model = model or self.llm or self.DEFAULT_STT_MODEL
        
        params = self._get_model_params(model)
        
        # Handle file input
        if isinstance(file, str):
            params["file"] = open(file, "rb")
        else:
            params["file"] = file
        
        if language:
            params["language"] = language
        elif self._audio_config.language:
            params["language"] = self._audio_config.language
            
        if temperature is not None:
            params["temperature"] = temperature
        elif self._audio_config.temperature != 0.0:
            params["temperature"] = self._audio_config.temperature
        
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Transcribing with {model}...[/cyan]")
        
        response = self.litellm.transcription(**params)
        
        # Close file if we opened it
        if isinstance(file, str):
            params["file"].close()
        
        text = response.text if hasattr(response, 'text') else str(response)
        
        if self.verbose:
            self.console.print(f"[green]✓ Transcription complete[/green]")
        
        return text
    
    async def atranscribe(
        self,
        file: Union[str, BinaryIO],
        language: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Async version of transcribe()."""
        model = model or self.llm or self.DEFAULT_STT_MODEL
        
        params = self._get_model_params(model)
        
        if isinstance(file, str):
            params["file"] = open(file, "rb")
        else:
            params["file"] = file
        
        if language:
            params["language"] = language
        elif self._audio_config.language:
            params["language"] = self._audio_config.language
            
        if temperature is not None:
            params["temperature"] = temperature
        
        params.update(kwargs)
        
        response = await self.litellm.atranscription(**params)
        
        if isinstance(file, str):
            params["file"].close()
        
        return response.text if hasattr(response, 'text') else str(response)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Convenience Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def say(self, text: str, output: str = "output.mp3", **kwargs) -> str:
        """
        Quick TTS - convert text and save to file.
        
        Args:
            text: Text to speak
            output: Output filename (default: output.mp3)
            
        Returns:
            Path to saved file
        """
        self.speech(text, output=output, **kwargs)
        return output
    
    async def asay(self, text: str, output: str = "output.mp3", **kwargs) -> str:
        """Async version of say()."""
        await self.aspeech(text, output=output, **kwargs)
        return output
    
    def listen(self, file: Union[str, BinaryIO], **kwargs) -> str:
        """
        Quick STT - transcribe audio file.
        
        Args:
            file: Audio file to transcribe
            
        Returns:
            Transcribed text
        """
        return self.transcribe(file, **kwargs)
    
    async def alisten(self, file: Union[str, BinaryIO], **kwargs) -> str:
        """Async version of listen()."""
        return await self.atranscribe(file, **kwargs)
