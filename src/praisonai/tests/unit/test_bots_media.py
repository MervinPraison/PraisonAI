"""
Unit tests for bot media parsing utilities.
"""
import os
import tempfile
import pytest

from praisonai.bots.media import split_media_from_output, is_audio_file


class TestSplitMediaFromOutput:
    """Tests for split_media_from_output function."""
    
    def test_empty_text(self):
        """Empty text returns empty result."""
        result = split_media_from_output("")
        assert result["text"] == ""
        assert result["media_urls"] == []
        assert result["audio_as_voice"] is False
    
    def test_text_only(self):
        """Text without MEDIA: is preserved."""
        result = split_media_from_output("Hello world!")
        assert result["text"] == "Hello world!"
        assert result["media_urls"] == []
        assert result["audio_as_voice"] is False
    
    def test_media_with_existing_file(self):
        """MEDIA: with existing file is extracted."""
        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
        
        try:
            result = split_media_from_output(f"Hello\nMEDIA:{temp_path}\nWorld")
            assert "Hello" in result["text"]
            assert "World" in result["text"]
            assert temp_path in result["media_urls"]
        finally:
            os.unlink(temp_path)
    
    def test_voice_tag_detection(self):
        """[[audio_as_voice]] tag is detected and removed."""
        result = split_media_from_output("[[audio_as_voice]] Hello!")
        assert result["audio_as_voice"] is True
        assert "[[audio_as_voice]]" not in result["text"]
        assert "Hello" in result["text"]
    
    def test_multiple_media_urls(self):
        """Multiple MEDIA: lines are all extracted."""
        # Create temp files
        temps = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temps.append(f.name)
        
        try:
            text = f"Start\nMEDIA:{temps[0]}\nMiddle\nMEDIA:{temps[1]}\nEnd"
            result = split_media_from_output(text)
            assert len(result["media_urls"]) == 2
            assert temps[0] in result["media_urls"]
            assert temps[1] in result["media_urls"]
        finally:
            for t in temps:
                os.unlink(t)
    
    def test_http_url(self):
        """HTTP URLs are accepted as media."""
        result = split_media_from_output("MEDIA:https://example.com/audio.mp3")
        assert "https://example.com/audio.mp3" in result["media_urls"]


class TestIsAudioFile:
    """Tests for is_audio_file function."""
    
    def test_audio_extensions(self):
        """Audio extensions are recognized."""
        assert is_audio_file("/path/to/file.mp3") is True
        assert is_audio_file("/path/to/file.wav") is True
        assert is_audio_file("/path/to/file.ogg") is True
        assert is_audio_file("/path/to/file.opus") is True
        assert is_audio_file("/path/to/file.m4a") is True
    
    def test_non_audio_extensions(self):
        """Non-audio extensions are rejected."""
        assert is_audio_file("/path/to/file.txt") is False
        assert is_audio_file("/path/to/file.pdf") is False
        assert is_audio_file("/path/to/file.png") is False
