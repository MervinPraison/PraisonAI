"""HeyGen + ElevenLabs Video Generation Example.

Generate an AI avatar video using HeyGen with ElevenLabs voice.
The agent autonomously: generates audio → uploads to HeyGen → creates video → waits for completion.

Required env vars:
    HEYGEN_API_KEY: HeyGen API key (https://app.heygen.com/settings/api)
    ELEVENLABS_API_KEY: ElevenLabs API key (https://elevenlabs.io)
    OPENAI_API_KEY: OpenAI API key (for the agent LLM)

Usage:
    export HEYGEN_API_KEY=your_key
    export ELEVENLABS_API_KEY=your_key
    export OPENAI_API_KEY=your_key
    python video_heygen_elevenlabs.py
"""

from praisonaiagents import Agent
from praisonai_tools import (
    elevenlabs_speak_to_file,
    heygen_upload_asset,
    heygen_generate_video_with_audio,
    heygen_wait_for_video,
)

agent = Agent(
    name="Video Producer",
    instructions="""You create AI avatar videos. Follow these steps:

Step 1: Call elevenlabs_speak_to_file with text and output_path="/tmp/speech.mp3"
Step 2: Call heygen_upload_asset with file_path="/tmp/speech.mp3", content_type="audio/mpeg"
Step 3: Call heygen_generate_video_with_audio with the avatar_id and audio_asset_id from Step 2
Step 4: Call heygen_wait_for_video with the video_id from Step 3
Step 5: Report the final video URL
""",
    tools=[
        elevenlabs_speak_to_file,
        heygen_upload_asset,
        heygen_generate_video_with_audio,
        heygen_wait_for_video,
    ],
)

result = agent.start(
    'Create a video with this script: "Welcome to PraisonAI! '
    'Build powerful AI agents in just three lines of code." '
    'Use avatar_id: "YOUR_AVATAR_ID"'
)
print(result)
