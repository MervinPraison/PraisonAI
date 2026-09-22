"""Opt-in real text inference alongside an image call with a local provider stub."""

import asyncio
import os
import threading

import pytest


@pytest.mark.live
@pytest.mark.asyncio
async def test_text_agent_runs_alongside_async_image_generation(monkeypatch):
    from praisonaiagents import Agent, ImageAgent

    loop = asyncio.get_running_loop()
    released = threading.Event()
    image_result = {"data": [{"url": "https://example.com/landscape.png"}]}

    def image_provider(**kwargs):
        assert kwargs["prompt"] == "A mountain landscape"
        loop.call_soon_threadsafe(released.set)
        if not released.wait(timeout=5):
            raise RuntimeError("Image provider blocked the event loop")
        return image_result

    options = dict(
        instructions="Give a brief answer.",
        llm={"model": os.environ.get("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini"), "max_tokens": 96},
        reflection=False, memory=False, rules=False, output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with ImageAgent(llm="openai/dall-e-3", instructions="Create images", verbose=False) as artist, Agent(**options) as writer:
        monkeypatch.setattr(artist, "_litellm", image_provider)
        image, answer = await asyncio.gather(
            artist.agenerate_image("A mountain landscape"),
            asyncio.to_thread(writer.start, "Write one short caption for a mountain landscape."),
        )
        print("Full Agent.start output:", answer)
        assert image == image_result
        assert isinstance(answer, str) and answer.strip()
