"""Linear GraphQL tools — lazy, opt-in, no heavy module-level deps."""
import json
import logging
import os
from typing import Any, Dict, List, Optional
from .decorator import tool

logger = logging.getLogger(__name__)

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


def _auth_header() -> Dict[str, str]:
    """Get authorization header from environment."""
    key = os.environ.get("LINEAR_API_KEY") or os.environ.get("LINEAR_OAUTH_TOKEN")
    if not key:
        raise RuntimeError(
            "Set LINEAR_API_KEY (personal) or LINEAR_OAUTH_TOKEN (OAuth)"
        )
    return {"Authorization": key, "Content-Type": "application/json"}


async def _gql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute GraphQL query against Linear API."""
    import aiohttp  # lazy import
    async with aiohttp.ClientSession() as s:
        async with s.post(
            _LINEAR_ENDPOINT,
            headers=_auth_header(),
            data=json.dumps({"query": query, "variables": variables or {}}),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json()
            if "errors" in data:
                raise RuntimeError(f"Linear GQL error: {data['errors']}")
            return data.get("data", {})


@tool
async def linear_search_issues(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search Linear issues by text. Returns list of {id, identifier, title, state, url}."""
    q = """query($q: String!, $first: Int!) {
      issueSearch(query: $q, first: $first) {
        nodes { id identifier title url state { name } }
      }
    }"""
    d = await _gql(q, {"q": query, "first": limit})
    return d.get("issueSearch", {}).get("nodes", [])


@tool
async def linear_get_issue(issue_id: str) -> Dict[str, Any]:
    """Get a single Linear issue by UUID or identifier (e.g. 'ENG-123')."""
    q = """query($id: String!) {
      issue(id: $id) {
        id identifier title description url priority
        state { name } assignee { id name } team { id key }
        comments { nodes { id body user { name } } }
      }
    }"""
    d = await _gql(q, {"id": issue_id})
    return d.get("issue", {})


@tool
async def linear_create_issue(
    team_id: str,
    title: str,
    description: str = "",
    priority: int = 0,
    assignee_id: Optional[str] = None,
    label_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new Linear issue. Returns {id, identifier, url}."""
    q = """mutation($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success issue { id identifier url }
      }
    }"""
    inp = {"teamId": team_id, "title": title, "description": description, "priority": priority}
    if assignee_id: 
        inp["assigneeId"] = assignee_id
    if label_ids: 
        inp["labelIds"] = label_ids
    d = await _gql(q, {"input": inp})
    return d.get("issueCreate", {}).get("issue", {})


@tool
async def linear_update_issue(issue_id: str, state_id: Optional[str] = None, **fields) -> bool:
    """Update a Linear issue (move state, change title, etc.)."""
    q = """mutation($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) { success }
    }"""
    inp = dict(fields)
    if state_id: 
        inp["stateId"] = state_id
    d = await _gql(q, {"id": issue_id, "input": inp})
    return bool(d.get("issueUpdate", {}).get("success"))


@tool
async def linear_add_comment(issue_id: str, body: str) -> Dict[str, Any]:
    """Add a comment to a Linear issue (posted as app user when OAuth actor=app)."""
    q = """mutation($input: CommentCreateInput!) {
      commentCreate(input: $input) { success comment { id url } }
    }"""
    d = await _gql(q, {"input": {"issueId": issue_id, "body": body}})
    return d.get("commentCreate", {}).get("comment", {})


@tool
async def linear_list_cycles(team_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """List cycles (sprints) for a team — useful for 'work everything in current cycle'."""
    q = """query($id: String!, $first: Int!) {
      team(id: $id) { cycles(first: $first) { nodes { id name number startsAt endsAt } } }
    }"""
    d = await _gql(q, {"id": team_id, "first": limit})
    return d.get("team", {}).get("cycles", {}).get("nodes", [])


@tool  
async def linear_list_teams() -> List[Dict[str, Any]]:
    """List all teams in the workspace. Returns list of {id, key, name}."""
    q = """query {
      teams { nodes { id key name } }
    }"""
    d = await _gql(q)
    return d.get("teams", {}).get("nodes", [])


@tool
async def linear_list_issue_states(team_id: str) -> List[Dict[str, Any]]:
    """List workflow states for a team. Returns list of {id, name, type}."""
    q = """query($id: String!) {
      team(id: $id) { states { nodes { id name type } } }
    }"""
    d = await _gql(q, {"id": team_id})
    return d.get("team", {}).get("states", {}).get("nodes", [])