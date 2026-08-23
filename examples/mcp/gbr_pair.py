"""
Build Remote Agent pairing example.

Pair a phone (Build Remote Agent) to this PraisonAI session through the
free MIT gbr-agent. Protocol gbr/1. Phone is spectator + veto.

Requirements:
    - gbr-agent v0.6.0+ (`gbr-agent pair && gbr-agent run`)
    - GrokBuildRemote-Agents cloned; `npm install` in mcp/gbr-mcp
    - pip install praisonaiagents[mcp]

Usage:
    python gbr_pair.py

Never put mailbox keys in this file. Phone Settings → Bot API is the
only place the relay key is copied.

Independent product by Linespotting AB. Not affiliated with xAI or SpaceX.
https://grokbuildremote.com/
"""

import os

from praisonaiagents import Agent, MCP

# Clone https://github.com/LinespottingOrg/GrokBuildRemote-Agents.git then point
# GBR_MCP_JS at mcp/gbr-mcp/bin/gbr-mcp.js (loopback stdio). Resolved to an
# absolute path so the example runs from any working directory. Override with:
#     export GBR_MCP_JS=/abs/path/to/GrokBuildRemote-Agents/mcp/gbr-mcp/bin/gbr-mcp.js
GBR_MCP_JS = os.path.abspath(
    os.environ.get(
        "GBR_MCP_JS",
        "GrokBuildRemote-Agents/mcp/gbr-mcp/bin/gbr-mcp.js",
    )
)

gbr = Agent(
    instructions=(
        "You can attach a phone spectator via Build Remote Agent. "
        "Use GBR tools only to diagnose or attach the local Bot API "
        "at 127.0.0.1:8788. Do not request mailbox keys."
    ),
    llm="gpt-4o-mini",
    tools=MCP("node", args=[GBR_MCP_JS]),
)

if __name__ == "__main__":
    gbr.start(
        "Check Build Remote Agent health on 127.0.0.1:8788 and list sessions."
    )
