"""
Audio Capabilities Example

Demonstrates transcription and text-to-speech using PraisonAI capabilities.
"""

from praisonai.capabilities import transcribe, speech

# Note: Audio transcription requires an audio file
# This example shows the API structure

print("=== Audio Transcription ===")
print("To transcribe audio, use:")
print("  result = transcribe('audio.mp3', model='whisper-1')")
print("  print(result.text)")

print("\n=== Text-to-Speech ===")
print("To generate speech, use:")
print("  audio_data = speech('Hello world', model='tts-1', voice='alloy')")
print("  # Save to file or play")

print("\nNote: These operations require audio files or generate audio output.")
print("See CLI: praisonai audio transcribe <file>")
print("See CLI: praisonai audio speech <text>")
