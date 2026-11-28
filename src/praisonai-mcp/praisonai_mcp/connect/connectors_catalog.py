"""Official remote MCP connector catalog (verified vendor Streamable HTTP URLs)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass(frozen=True)
class ConnectorEntry:
    id: str
    label: str
    url: str
    oauth: bool = True
    docs_url: str = ""

CONNECTOR_CATALOG: Dict[str, ConnectorEntry] = {
    e.id: e for e in (
        ConnectorEntry("github", "GitHub", "https://api.githubcopilot.com/mcp/", True, "https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server"),
        ConnectorEntry("linear", "Linear", "https://mcp.linear.app/mcp", True, "https://linear.app/docs/mcp"),
        ConnectorEntry("notion", "Notion", "https://mcp.notion.com/mcp", True, "https://developers.notion.com/docs/mcp"),
        ConnectorEntry("atlassian", "Atlassian", "https://mcp.atlassian.com/v2/mcp", True, "https://support.atlassian.com/atlassian-rovo-mcp-server/"),
        ConnectorEntry("sentry", "Sentry", "https://mcp.sentry.dev/mcp", True, "https://docs.sentry.io/product/sentry-mcp/"),
        ConnectorEntry("stripe", "Stripe", "https://mcp.stripe.com", True, "https://docs.stripe.com/mcp"),
        ConnectorEntry("cloudflare", "Cloudflare", "https://mcp.cloudflare.com/mcp", True, "https://developers.cloudflare.com/agents/model-context-protocol/"),
        ConnectorEntry("vercel", "Vercel", "https://mcp.vercel.com", True, "https://vercel.com/docs/mcp/vercel-mcp"),
        ConnectorEntry("deepwiki", "DeepWiki", "https://mcp.deepwiki.com/mcp", False, "https://docs.devin.ai/work-with-devin/deepwiki-mcp"),
        ConnectorEntry("openai-docs", "OpenAI Docs", "https://developers.openai.com/mcp", False, "https://developers.openai.com/api/docs/guides/tools-connectors-mcp"),
    )
}

def list_connectors() -> List[ConnectorEntry]:
    return list(CONNECTOR_CATALOG.values())

def get_connector(name: str) -> Optional[ConnectorEntry]:
    return CONNECTOR_CATALOG.get((name or "").strip().lower())
