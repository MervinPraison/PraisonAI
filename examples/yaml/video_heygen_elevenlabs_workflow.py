#!/usr/bin/env python3
"""Run the HeyGen + ElevenLabs YAML workflow.

This loads the YAML workflow and registers the praisonai_tools
functions so the YAML parser can resolve them by name.

Usage:
    export HEYGEN_API_KEY=your_key
    export ELEVENLABS_API_KEY=your_key
    export OPENAI_API_KEY=your_key
    python video_heygen_elevenlabs_workflow.py
"""

import os
from pathlib import Path

from praisonai_tools import (
    elevenlabs_speak_to_file,
    heygen_upload_asset,
    heygen_generate_video_with_audio,
    heygen_wait_for_video,
)
from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

# Register praisonai_tools functions for YAML tool resolution
tool_registry = {
    "elevenlabs_speak_to_file": elevenlabs_speak_to_file,
    "heygen_upload_asset": heygen_upload_asset,
    "heygen_generate_video_with_audio": heygen_generate_video_with_audio,
    "heygen_wait_for_video": heygen_wait_for_video,
}

# Parse YAML workflow
yaml_path = Path(__file__).parent / "video_heygen_elevenlabs.yaml"
parser = YAMLWorkflowParser(tool_registry=tool_registry)
workflow = parser.parse_file(yaml_path)

print("=" * 60)
print("HeyGen + ElevenLabs YAML Workflow")
print("=" * 60)

# Run the workflow
result = workflow.start()

print("\n" + "=" * 60)
print("WORKFLOW RESULT:")
print("=" * 60)
print(result)
