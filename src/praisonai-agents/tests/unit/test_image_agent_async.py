"""Async image calls must let other event-loop callbacks make progress."""

import asyncio
import threading

import pytest

from praisonaiagents import ImageAgent


CALLS = [
    ("agenerate_image", "generate_image", ("A landscape",), {"quality": "hd"}),
    ("agenerate", "generate_image", ("A landscape",), {"quality": "hd"}),
    ("achat", "generate_image", ("A landscape",), {"quality": "hd"}),
    ("aedit", "edit", ("source.png", "Add clouds", "mask.png", 2, "512x512"), {"quality": "hd"}),
    ("avariation", "variation", ("source.png", 2, "512x512"), {"response_format": "b64_json"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("async_name,sync_name,args,kwargs", CALLS)
@pytest.mark.parametrize("provider_error", [False, True])
async def test_image_call_allows_loop_progress(monkeypatch, async_name, sync_name, args, kwargs, provider_error):
    agent = ImageAgent(llm="openai/dall-e-3", instructions="Create images", verbose=False)
    loop = asyncio.get_running_loop()
    released = threading.Event()
    result = {"data": [{"url": "https://example.com/image.png"}]}
    received = []

    def blocking_call(*call_args, **call_kwargs):
        received.append((call_args, call_kwargs))
        loop.call_soon_threadsafe(released.set)
        if not released.wait(timeout=2):
            raise RuntimeError("Image call blocked the event loop")
        if provider_error:
            raise ValueError("Image provider unavailable")
        return result

    monkeypatch.setattr(agent, sync_name, blocking_call)
    try:
        if provider_error and async_name != "achat":
            with pytest.raises(ValueError, match="Image provider unavailable"):
                await getattr(agent, async_name)(*args, **kwargs)
        else:
            answer = await getattr(agent, async_name)(*args, **kwargs)
            assert answer == ({"error": "Image provider unavailable"} if provider_error else result)
        assert received == [(args, kwargs)]
    finally:
        released.set()
        agent.close()
