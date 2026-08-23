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

from praisonaiagents import Agent, MCP

# Clone https://github.com/LinespottingOrg/GrokBuildRemote-Agents.git
# then point args at mcp/gbr-mcp/bin/gbr-mcp.js (loopback stdio).
gbr = Agent(
    instructions=(
        "You can attach a phone spectator via Build Remote Agent. "
        "Use GBR tools only to diagnose or attach the local Bot API "
        "at 127.0.0.1:8788. Do not request mailbox keys."
    ),
    llm="gpt-4o-mini",
    tools=MCP(
        "node",
        args=["GrokBuildRemote-Agents/mcp/gbr-mcp/bin/gbr-mcp.js"],
    ),
)

if __name__ == "__main__":
    gbr.start(
        "Check Build Remote Agent health on 127.0.0.1:8788 and list sessions."
    )
