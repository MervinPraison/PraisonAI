# Video Generation with OpenAI Sora
# Requires: export OPENAI_API_KEY=your-key
# Note: Sora requires organization verification

from praisonaiagents import VideoAgent

agent = VideoAgent(llm="openai/sora-2")
video = agent.generate("A cat playing with yarn")
print(f"Video ID: {video.id}")
