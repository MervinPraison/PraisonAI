"""Concurrent AG-UI runs on one agent must not receive each other's tokens (#6150)."""

import asyncio

from praisonaiagents.streaming.events import StreamEvent, StreamEventEmitter, StreamEventType
from praisonaiagents.ui.agui.streaming import async_stream_agent_response


class _AsyncAgent:
    def __init__(self):
        self.stream_emitter = StreamEventEmitter()

    async def achat(self, text, stream=True):
        for tok in (f"[{text}-1]", f"[{text}-2]"):
            self.stream_emitter.emit(StreamEvent(type=StreamEventType.DELTA_TEXT, content=tok))
            await asyncio.sleep(0.02)
        return text


class _SyncAgent:
    def __init__(self):
        self.stream_emitter = StreamEventEmitter()

    def chat(self, text, stream=True):
        import time
        for tok in (f"[{text}-1]", f"[{text}-2]"):
            self.stream_emitter.emit(StreamEvent(type=StreamEventType.DELTA_TEXT, content=tok))
            time.sleep(0.02)
        return text


async def _collect(agent, who):
    out = []
    async for ev in async_stream_agent_response(agent, who, "th-" + who, "run-" + who):
        if getattr(ev, "delta", None):
            out.append(ev.delta)
    return "".join(out)


def _run_pair(agent):
    async def main():
        return await asyncio.gather(_collect(agent, "ALICE"), _collect(agent, "BOB"))
    return asyncio.run(main())


def test_concurrent_async_runs_do_not_leak_tokens():
    alice, bob = _run_pair(_AsyncAgent())
    assert alice == "[ALICE-1][ALICE-2]"
    assert bob == "[BOB-1][BOB-2]"


def test_concurrent_sync_runs_do_not_leak_tokens():
    alice, bob = _run_pair(_SyncAgent())
    assert alice == "[ALICE-1][ALICE-2]"
    assert bob == "[BOB-1][BOB-2]"
