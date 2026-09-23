"""OpenRouter video generation via VideoAgent.

Requires OPENROUTER_API_KEY. Optionally set OPENROUTER_REFERER and
OPENROUTER_APP_TITLE for OpenRouter dashboard attribution.

The openrouter/ prefix is required so the request routes to OpenRouter.
Discover exact model ids at https://openrouter.ai/api/v1/videos/models.
"""

from praisonaiagents import VideoAgent

agent = VideoAgent(llm="openrouter/google/veo-3.1")

video = agent.generate(
    "A serene mountain landscape at sunset, locked camera",
    duration=6,
    resolution="720p",
    aspect_ratio="16:9",
    generate_audio=False,
)
print(f"Video ID: {video.id}")

completed = agent.wait_for_completion(video.id)
if completed.status == "completed":
    agent.download(video.id, "openrouter_veo.mp4")
    print("Saved openrouter_veo.mp4")
else:
    print(f"Generation ended with status: {completed.status}")
