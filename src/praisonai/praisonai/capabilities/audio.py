"""
Audio Capabilities Module

Provides audio transcription and text-to-speech functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, BinaryIO, Dict


@dataclass
class TranscriptionResult:
    """Result from audio transcription."""
    text: str
    duration: Optional[float] = None
    language: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None
    words: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpeechResult:
    """Result from text-to-speech."""
    audio: bytes
    content_type: str = "audio/mpeg"
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def save(self, path: str) -> str:
        """Save audio to file."""
        with open(path, 'wb') as f:
            f.write(self.audio)
        return path


def transcribe(
    audio: Union[str, bytes, BinaryIO],
    model: str = "whisper-1",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    response_format: str = "json",
    temperature: float = 0.0,
    timestamp_granularities: Optional[List[str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> TranscriptionResult:
    """
    Transcribe audio to text using LiteLLM.
    
    Args:
        audio: File path, bytes, or file-like object
        model: Model name (e.g., "whisper-1", "deepgram/nova-2")
        language: ISO language code (e.g., "en", "es")
        prompt: Optional prompt to guide transcription
        response_format: "json", "text", "srt", "verbose_json", "vtt"
        temperature: Sampling temperature (0.0-1.0)
        timestamp_granularities: List of "word" and/or "segment"
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing (agent_id, session_id, etc.)
        
    Returns:
        TranscriptionResult with text and optional metadata
        
    Example:
        >>> result = transcribe("./audio.mp3")
        >>> print(result.text)
        
        >>> result = transcribe("./audio.mp3", model="deepgram/nova-2", language="en")
        >>> print(result.text)
    """
    import litellm
    
    # Handle file path
    file_obj = audio
    if isinstance(audio, str):
        file_obj = open(audio, 'rb')
    
    try:
        # Build kwargs for litellm
        call_kwargs = {
            'model': model,
            'file': file_obj,
            'timeout': timeout,
        }
        
        if language:
            call_kwargs['language'] = language
        if prompt:
            call_kwargs['prompt'] = prompt
        if response_format:
            call_kwargs['response_format'] = response_format
        if temperature is not None:
            call_kwargs['temperature'] = temperature
        if timestamp_granularities:
            call_kwargs['timestamp_granularities'] = timestamp_granularities
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        # Add any extra kwargs
        call_kwargs.update(kwargs)
        
        # Add metadata for tracing
        if metadata:
            call_kwargs['metadata'] = metadata
        
        response = litellm.transcription(**call_kwargs)
        
        return TranscriptionResult(
            text=getattr(response, 'text', str(response)),
            duration=getattr(response, 'duration', None),
            language=getattr(response, 'language', language),
            segments=getattr(response, 'segments', None),
            words=getattr(response, 'words', None),
            model=model,
            metadata=metadata or {},
        )
    finally:
        # Close file if we opened it
        if isinstance(audio, str) and hasattr(file_obj, 'close'):
            file_obj.close()


async def atranscribe(
    audio: Union[str, bytes, BinaryIO],
    model: str = "whisper-1",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    response_format: str = "json",
    temperature: float = 0.0,
    timestamp_granularities: Optional[List[str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> TranscriptionResult:
    """
    Async: Transcribe audio to text using LiteLLM.
    
    See transcribe() for full documentation.
    """
    import litellm
    
    # Handle file path
    file_obj = audio
    if isinstance(audio, str):
        file_obj = open(audio, 'rb')
    
    try:
        # Build kwargs for litellm
        call_kwargs = {
            'model': model,
            'file': file_obj,
            'timeout': timeout,
        }
        
        if language:
            call_kwargs['language'] = language
        if prompt:
            call_kwargs['prompt'] = prompt
        if response_format:
            call_kwargs['response_format'] = response_format
        if temperature is not None:
            call_kwargs['temperature'] = temperature
        if timestamp_granularities:
            call_kwargs['timestamp_granularities'] = timestamp_granularities
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        call_kwargs.update(kwargs)
        
        if metadata:
            call_kwargs['metadata'] = metadata
        
        response = await litellm.atranscription(**call_kwargs)
        
        return TranscriptionResult(
            text=getattr(response, 'text', str(response)),
            duration=getattr(response, 'duration', None),
            language=getattr(response, 'language', language),
            segments=getattr(response, 'segments', None),
            words=getattr(response, 'words', None),
            model=model,
            metadata=metadata or {},
        )
    finally:
        if isinstance(audio, str) and hasattr(file_obj, 'close'):
            file_obj.close()


def speech(
    text: str,
    model: str = "tts-1",
    voice: str = "alloy",
    response_format: str = "mp3",
    speed: float = 1.0,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> SpeechResult:
    """
    Convert text to speech using LiteLLM.
    
    Args:
        text: Text to convert to speech
        model: Model name (e.g., "tts-1", "tts-1-hd", "elevenlabs/...")
        voice: Voice name (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")
        response_format: "mp3", "opus", "aac", "flac", "wav", "pcm"
        speed: Speed multiplier (0.25-4.0)
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        SpeechResult with audio bytes
        
    Example:
        >>> result = speech("Hello, world!")
        >>> result.save("output.mp3")
        
        >>> result = speech("Hello!", voice="nova", speed=1.2)
        >>> with open("output.mp3", "wb") as f:
        ...     f.write(result.audio)
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': text,
        'voice': voice,
        'response_format': response_format,
        'speed': speed,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.speech(**call_kwargs)
    
    # Get audio content
    audio_content = response.content if hasattr(response, 'content') else bytes(response)
    
    return SpeechResult(
        audio=audio_content,
        content_type=f"audio/{response_format}",
        model=model,
        metadata=metadata or {},
    )


async def aspeech(
    text: str,
    model: str = "tts-1",
    voice: str = "alloy",
    response_format: str = "mp3",
    speed: float = 1.0,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> SpeechResult:
    """
    Async: Convert text to speech using LiteLLM.
    
    See speech() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': text,
        'voice': voice,
        'response_format': response_format,
        'speed': speed,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.aspeech(**call_kwargs)
    
    audio_content = response.content if hasattr(response, 'content') else bytes(response)
    
    return SpeechResult(
        audio=audio_content,
        content_type=f"audio/{response_format}",
        model=model,
        metadata=metadata or {},
    )
