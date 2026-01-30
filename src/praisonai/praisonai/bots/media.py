"""
Media parsing utilities for bot responses.

Parses MEDIA: protocol from agent responses to extract audio/image paths.
Similar to moltbot's splitMediaFromOutput() pattern.
"""

import os
import re
from typing import Dict, List, Any

# Regex to match MEDIA:/path lines
MEDIA_REGEX = re.compile(r"^MEDIA:(.+)$", re.MULTILINE)

# Voice bubble control tag (Telegram)
VOICE_TAG = "[[audio_as_voice]]"


def split_media_from_output(text: str) -> Dict[str, Any]:
    """
    Extract MEDIA: paths from agent response text.
    
    Parses lines like:
        MEDIA:/tmp/tts_abc123.mp3
        [[audio_as_voice]]
    
    Args:
        text: Raw agent response text
        
    Returns:
        Dict with:
            - text: Cleaned text without MEDIA: lines
            - media_urls: List of extracted file paths
            - audio_as_voice: True if [[audio_as_voice]] tag present
            
    Example:
        >>> split_media_from_output("Hello\\nMEDIA:/tmp/audio.mp3")
        {"text": "Hello", "media_urls": ["/tmp/audio.mp3"], "audio_as_voice": False}
    """
    if not text:
        return {"text": "", "media_urls": [], "audio_as_voice": False}
    
    # Check for voice tag
    audio_as_voice = VOICE_TAG in text
    clean = text.replace(VOICE_TAG, "")
    
    # Extract media paths
    media_urls: List[str] = []
    for match in MEDIA_REGEX.finditer(clean):
        path = match.group(1).strip()
        # Remove quotes if present
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        elif path.startswith("'") and path.endswith("'"):
            path = path[1:-1]
        
        # Validate path exists or is URL
        if path and (os.path.exists(path) or path.startswith("http")):
            media_urls.append(path)
    
    # Remove MEDIA: lines from text
    clean = MEDIA_REGEX.sub("", clean)
    
    # Clean up whitespace
    clean = "\n".join(line for line in clean.split("\n") if line.strip())
    clean = clean.strip()
    
    return {
        "text": clean,
        "media_urls": media_urls,
        "audio_as_voice": audio_as_voice,
    }


def is_audio_file(path: str) -> bool:
    """Check if file path is an audio file by extension."""
    audio_extensions = {".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac"}
    return os.path.splitext(path.lower())[1] in audio_extensions
