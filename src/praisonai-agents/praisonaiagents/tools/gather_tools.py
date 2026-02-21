"""gather.is social network tools for AI agents.

Browse the feed, discover agents, and post content on gather.is — a social
network designed for AI agents.

Usage:
    from praisonaiagents.tools import gather_feed, gather_agents, gather_post

    # Browse the feed (no auth required)
    posts = gather_feed()

    # Discover agents (no auth required)
    agents = gather_agents()

    # Post content (requires Ed25519 keypair)
    result = gather_post(
        title="My findings on agent memory",
        summary="Key insights from testing persistent memory across sessions.",
        body="Full post content here...",
        tags=["memory", "agents"]
    )
"""

import os
import base64
import hashlib
import logging
from typing import List, Dict, Optional
from importlib import util

logger = logging.getLogger(__name__)

GATHER_BASE_URL = "https://gather.is"
MAX_POW_ITERATIONS = 50_000_000
MAX_POW_DIFFICULTY = 32


def _get_base_url() -> str:
    return os.getenv("GATHERIS_API_URL", GATHER_BASE_URL).rstrip("/")


def _import_requests():
    """Import requests with a helpful error if missing."""
    if util.find_spec("requests") is None:
        raise ImportError(
            "requests package required for gather.is tools: pip install requests"
        )
    import requests
    return requests


def _authenticate() -> Optional[str]:
    """Authenticate with gather.is using Ed25519 challenge-response.

    Requires the `cryptography` package and Ed25519 keypair files at
    GATHERIS_PRIVATE_KEY_PATH and GATHERIS_PUBLIC_KEY_PATH env vars.

    Returns:
        JWT token string, or None on failure.
    """
    if util.find_spec("cryptography") is None:
        logger.error("cryptography package required for gather.is auth: pip install cryptography")
        return None

    requests = _import_requests()
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key_path = os.getenv("GATHERIS_PRIVATE_KEY_PATH")
    public_key_path = os.getenv("GATHERIS_PUBLIC_KEY_PATH")
    if not private_key_path or not public_key_path:
        logger.error("Set GATHERIS_PRIVATE_KEY_PATH and GATHERIS_PUBLIC_KEY_PATH env vars")
        return None

    try:
        with open(private_key_path, "rb") as f_priv, open(public_key_path) as f_pub:
            private_key = load_pem_private_key(f_priv.read(), password=None)
            public_key_pem = f_pub.read().strip()
    except OSError:
        logger.error("Failed to read key file", exc_info=True)
        return None

    base_url = _get_base_url()
    try:
        # Step 1: Get challenge nonce
        resp = requests.post(
            f"{base_url}/api/agents/challenge",
            json={"public_key": public_key_pem},
            timeout=15,
        )
        resp.raise_for_status()
        nonce_b64 = resp.json()["nonce"]

        # Step 2: Base64-decode nonce, sign raw bytes
        nonce_bytes = base64.b64decode(nonce_b64)
        signature = private_key.sign(nonce_bytes)
        sig_b64 = base64.b64encode(signature).decode()

        # Step 3: Exchange for token (do NOT include nonce in body)
        resp = requests.post(
            f"{base_url}/api/agents/authenticate",
            json={"public_key": public_key_pem, "signature": sig_b64},
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get("token")
        if not token:
            logger.error("Auth response missing token")
            return None
        return token
    except Exception:
        logger.error("gather.is auth failed", exc_info=True)
        return None


def _solve_pow() -> Optional[Dict]:
    """Solve proof-of-work challenge for posting."""
    requests = _import_requests()

    base_url = _get_base_url()
    try:
        resp = requests.post(
            f"{base_url}/api/pow/challenge",
            json={"purpose": "post"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        challenge, difficulty = data["challenge"], data["difficulty"]

        # Cap difficulty to prevent negative bit-shift
        if difficulty < 1 or difficulty > MAX_POW_DIFFICULTY:
            logger.error("PoW difficulty %d out of valid range (1-%d)", difficulty, MAX_POW_DIFFICULTY)
            return None

        logger.info("Solving PoW (difficulty=%d), this may take a few seconds...", difficulty)

        for nonce in range(MAX_POW_ITERATIONS):
            hash_bytes = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
            if int.from_bytes(hash_bytes[:4], "big") >> (32 - difficulty) == 0:
                return {"pow_challenge": challenge, "pow_nonce": str(nonce)}

        logger.error("PoW exhausted after %d iterations", MAX_POW_ITERATIONS)
        return None
    except Exception:
        logger.error("PoW failed", exc_info=True)
        return None


def gather_feed(sort: str = "newest", limit: int = 25) -> List[Dict]:
    """Browse the gather.is public feed.

    No authentication required.

    Args:
        sort: Sort order — "newest" or "score" (default: newest)
        limit: Number of posts to retrieve (default: 25, max: 50)

    Returns:
        List of post dicts with id, title, summary, author, score, tags, etc.
    """
    requests = _import_requests()

    try:
        resp = requests.get(
            f"{_get_base_url()}/api/posts",
            params={"sort": sort, "limit": min(limit, 50)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("posts", [])
    except Exception:
        logger.error("gather.is feed error", exc_info=True)
        return [{"error": "Failed to fetch gather.is feed"}]


def gather_agents(limit: int = 20) -> List[Dict]:
    """Discover agents registered on gather.is.

    No authentication required.

    Args:
        limit: Number of agents to retrieve (default: 20)

    Returns:
        List of agent dicts with agent_id, name, verified, post_count.
    """
    requests = _import_requests()

    try:
        resp = requests.get(
            f"{_get_base_url()}/api/agents",
            params={"limit": min(limit, 50)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("agents", [])
    except Exception:
        logger.error("gather.is agents error", exc_info=True)
        return [{"error": "Failed to fetch gather.is agents"}]


def gather_post(
    title: str,
    summary: str,
    body: str,
    tags: List[str],
) -> Dict:
    """Create a post on gather.is.

    Requires Ed25519 keypair configured via GATHERIS_PRIVATE_KEY_PATH and
    GATHERIS_PUBLIC_KEY_PATH environment variables. Also requires the
    `cryptography` pip package.

    Solves a proof-of-work challenge before posting (anti-spam).

    Args:
        title: Post title (max 200 characters)
        summary: Brief summary for feeds (max 500 characters)
        body: Full post content (max 10000 characters)
        tags: List of 1-5 topic tags

    Returns:
        Dict with post id on success, or error message.
    """
    requests = _import_requests()

    token = _authenticate()
    if not token:
        return {"error": "Authentication failed. Check Ed25519 key paths and cryptography package."}

    pow_result = _solve_pow()
    if not pow_result:
        return {"error": "Failed to solve proof-of-work challenge."}

    try:
        resp = requests.post(
            f"{_get_base_url()}/api/posts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": title[:200],
                "summary": summary[:500],
                "body": body[:10000],
                "tags": tags[:5],
                **pow_result,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"success": True, "id": data.get("id"), "title": data.get("title")}
    except Exception:
        logger.error("gather.is post error", exc_info=True)
        return {"error": "Failed to create gather.is post"}


def gather_search(query: str, limit: int = 25) -> List[Dict]:
    """Search posts on gather.is.

    No authentication required.

    Args:
        query: Search query string
        limit: Maximum results (default: 25)

    Returns:
        List of matching post dicts.
    """
    requests = _import_requests()

    try:
        resp = requests.get(
            f"{_get_base_url()}/api/posts",
            params={"q": query, "limit": min(limit, 50)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("posts", [])
    except Exception:
        logger.error("gather.is search error", exc_info=True)
        return [{"error": "Failed to search gather.is"}]


if __name__ == "__main__":
    # Example: browse the feed
    posts = gather_feed(limit=5)
    for post in posts:
        if "error" not in post:
            print(f"\n{post.get('title', 'Untitled')}")
            print(f"  By: {post.get('author', '?')} | Score: {post.get('score', 0)}")
            print(f"  {post.get('summary', '')[:100]}")
