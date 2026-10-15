"""S2 · cold time to first response: import, build one agent, one mocked call.

usage: python first_response.py <scenarios/agent1/<fw>.py>
"""

import sys
import time

t0 = time.perf_counter()
from _guard import install_egress_guard  # noqa: E402

install_egress_guard()
from _common import emit, load, stub_stats  # noqa: E402

mod = load(sys.argv[1])
agent = mod.build([])
text = str(mod.ask(agent, "Say hello."))
elapsed_ms = (time.perf_counter() - t0) * 1e3

stats = stub_stats()
reply = stats["requests"][-1]["reply_nonce"] if stats["requests"] else None
emit({"ms": elapsed_ms, "requests": len(stats["requests"]),
      "ok": bool(reply) and reply in text})
