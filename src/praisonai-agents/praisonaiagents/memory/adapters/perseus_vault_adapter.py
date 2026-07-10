"""
Perseus Vault memory adapter for PraisonAI.

Wraps the `perseus-vault` MCP server (a single static binary — SQLite + FTS5 +
bundled ONNX embeddings, optional AES-256-GCM) to implement ``MemoryProtocol``.
Unlike the mem0/chroma/mongodb adapters this has **no third-party Python SDK
dependency**: it speaks JSON-RPC 2.0 over the binary's stdio `serve` transport
directly, matching Perseus Vault's zero-dependency, local-first design.

Short-term vs long-term memory map onto Perseus Vault entity *categories*
(``working`` and ``episodic`` by default), so the two tiers stay queryable and
independently resettable. Search uses hybrid retrieval (FTS5 + dense vector
fusion) via ``perseus_vault_recall``.

Perseus Vault: https://github.com/Perseus-Computing-LLC/perseus-vault
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


class _VaultStdioClient:
    """Minimal JSON-RPC 2.0 client over the perseus-vault `serve` stdio transport.

    Spawns `perseus-vault serve --db <path>` as a long-lived child and exchanges
    newline-delimited JSON-RPC messages over its stdin/stdout. Thread-safe: a
    single lock serializes request/response round-trips.
    """

    def __init__(self, binary: str, db_path: str, env: Optional[Dict[str, str]] = None,
                 encryption_key: Optional[str] = None, startup_timeout: float = 10.0):
        self._binary = binary
        self._db_path = db_path
        self._encryption_key = encryption_key
        self._env = {**os.environ, **(env or {})}
        # Reentrant: _request may recurse into _start (which calls _request
        # again during the handshake) while already holding the lock.
        self._lock = threading.RLock()
        self._id = 0
        self._proc: Optional[subprocess.Popen] = None
        self._startup_timeout = startup_timeout
        self._start()

    def _start(self) -> None:
        cmd = [self._binary, "serve", "--db", self._db_path]
        if self._encryption_key:
            cmd += ["--encryption-key", self._encryption_key]
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, env=self._env,
        )
        # Handshake: initialize + notifications/initialized.
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "praisonai-perseus-vault", "version": "0.1.0"},
        })
        self._notify("notifications/initialized", {})

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _readline_with_timeout(self, timeout: float) -> Optional[str]:
        """Read one line from stdout, giving up after ``timeout`` seconds.

        A plain ``readline()`` blocks forever if the child accepts the request
        but never emits a newline, which would hang every subsequent memory
        call while the lock is held. Reading on a daemon thread lets the
        deadline actually fire and surface a ``TimeoutError``.
        """
        assert self._proc and self._proc.stdout
        result: List[Optional[str]] = [None]

        def _read() -> None:
            try:
                result[0] = self._proc.stdout.readline()
            except Exception:
                result[0] = None

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return result[0]

    def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            rid = self._next_id()
            msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            assert self._proc and self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            # Read until we get the response with our id (skip notifications).
            deadline = time.time() + self._startup_timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._teardown()
                    raise TimeoutError(
                        f"perseus-vault did not respond to {method} in time"
                    )
                line = self._readline_with_timeout(remaining)
                if line is None:
                    # Timed out mid-read. The daemon reader thread is still
                    # blocked on this stdout, so we must NOT reuse the process:
                    # a later call would race two readers on the same stream and
                    # one could steal the other's response. Tear the child down
                    # so the next _request() spawns a clean one.
                    self._teardown()
                    raise TimeoutError(
                        f"perseus-vault did not respond to {method} in time"
                    )
                if line == "":
                    raise RuntimeError("perseus-vault closed stdout unexpectedly")
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if resp.get("id") == rid:
                    if "error" in resp and resp["error"]:
                        raise RuntimeError(f"perseus-vault error: {resp['error']}")
                    return resp.get("result", {})

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        with self._lock:
            assert self._proc and self._proc.stdin
            msg = {"jsonrpc": "2.0", "method": method, "params": params}
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke an MCP tool; return the parsed JSON body of the first content item."""
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        if not content:
            return result
        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    def _teardown(self) -> None:
        """Forcibly terminate the child process. Used both on close and after a
        read timeout, where a daemon reader thread may still be attached to the
        old stdout — killing the process unblocks it and guarantees the next
        _request() starts from a clean subprocess."""
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def close(self) -> None:
        with self._lock:
            self._teardown()


class PerseusVaultMemoryAdapter:
    """Memory adapter backing PraisonAI with a local Perseus Vault MCP server.

    Recognised config keys (top level or nested under ``"config"``, mirroring the
    mem0/dakera adapters):

    - ``binary`` / ``bin``: path to the ``perseus-vault`` binary
      (falls back to ``PERSEUS_VAULT_BIN`` env, then ``"perseus-vault"`` on PATH).
    - ``db_path`` / ``db``: SQLite DB path
      (falls back to ``PERSEUS_VAULT_DB`` env, then ``"./perseus-vault.db"``).
    - ``encryption_key``: path to an AES-256-GCM key file
      (falls back to ``PERSEUS_VAULT_ENCRYPTION_KEY`` env; optional).
    - ``short_term_category`` / ``long_term_category``: entity categories used for
      the two tiers (default ``"working"`` and ``"episodic"``).
    - ``search_mode``: ``"hybrid"`` (default), ``"fts5"``, or ``"dense"``.
    - ``default_importance``: initial importance 0.0-1.0 for stored entities
      (default ``0.5``).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, client: Any = None, **kwargs):
        cfg = dict(config or {})
        cfg.update(kwargs)
        inner = cfg.get("config")
        if isinstance(inner, dict):
            cfg = {**inner, **{k: v for k, v in cfg.items() if k != "config"}}

        self._binary = cfg.get("binary") or cfg.get("bin") \
            or os.getenv("PERSEUS_VAULT_BIN", "perseus-vault")
        self._db_path = cfg.get("db_path") or cfg.get("db") \
            or os.getenv("PERSEUS_VAULT_DB", "./perseus-vault.db")
        self._encryption_key = cfg.get("encryption_key") \
            or os.getenv("PERSEUS_VAULT_ENCRYPTION_KEY")
        self._st_cat = cfg.get("short_term_category", "working")
        self._lt_cat = cfg.get("long_term_category", "episodic")
        self._search_mode = cfg.get("search_mode", "hybrid")
        if self._search_mode not in ("hybrid", "fts5", "dense"):
            raise ValueError(
                f"search_mode must be one of 'hybrid', 'fts5', 'dense'; "
                f"got {self._search_mode!r}"
            )
        try:
            self._default_importance = float(cfg.get("default_importance", 0.5))
        except (TypeError, ValueError):
            raise ValueError(
                f"default_importance must be a number in [0.0, 1.0]; "
                f"got {cfg.get('default_importance')!r}"
            )
        if not (0.0 <= self._default_importance <= 1.0):
            raise ValueError(
                f"default_importance must be in [0.0, 1.0]; "
                f"got {self._default_importance!r}"
            )

        # `client` is injectable for testing; otherwise spawn the real binary.
        self._client = client if client is not None else _VaultStdioClient(
            self._binary, self._db_path, env=cfg.get("env"),
            encryption_key=self._encryption_key,
        )

    # -- internal helpers ---------------------------------------------------

    def _store(self, category: str, text: str, metadata: Optional[Dict[str, Any]],
               **kwargs) -> str:
        key = (metadata or {}).get("key") or f"{category}-{uuid.uuid4().hex[:12]}"
        body = {"content": text}
        if metadata:
            body["metadata"] = metadata
        # Honour a caller-supplied importance (kwargs win over metadata), like
        # the dakera adapter, rather than always using the default.
        importance = kwargs.get("importance")
        if importance is None and metadata:
            importance = metadata.get("importance")
        importance = self._default_importance if importance is None else float(importance)
        self._client.call_tool("perseus_vault_remember", {
            "category": category,
            "key": key,
            "body_json": json.dumps(body),
            "importance": importance,
        })
        return key

    def _search(self, category: str, query: str, limit: int) -> List[Dict[str, Any]]:
        res = self._client.call_tool("perseus_vault_recall", {
            "query": query,
            "category": category,
            "limit": limit,
            "mode": self._search_mode,
        })
        items = res.get("items", []) if isinstance(res, dict) else []
        out: List[Dict[str, Any]] = []
        for it in items:
            body = it.get("body_json") or it.get("body") or {}
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    body = {"content": body}
            score = it.get("score")
            if score is None:
                score = it.get("confidence")
            out.append({
                "id": it.get("key") or it.get("id"),
                "text": body.get("content", ""),
                # Callers treat metadata as a dict and score as numeric, so
                # never surface None for either.
                "metadata": body.get("metadata") or {},
                "score": score if score is not None else 1.0,
            })
        return out

    # -- MemoryProtocol -----------------------------------------------------

    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        return self._store(self._st_cat, text, metadata, **kwargs)

    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        return self._search(self._st_cat, query, limit)

    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        return self._store(self._lt_cat, text, metadata, **kwargs)

    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        return self._search(self._lt_cat, query, limit)

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        # Enumerate both tiers. An empty query returns all entities in a
        # category (ordered by the vault's recency/decay ranking).
        results: List[Dict[str, Any]] = []
        limit = kwargs.get("limit", 100)
        for cat in (self._st_cat, self._lt_cat):
            results.extend(self._search(cat, "", limit))
        return results

    def reset_short_term(self) -> None:
        self._reset_category(self._st_cat)

    def reset_long_term(self) -> None:
        self._reset_category(self._lt_cat)

    def _reset_category(self, category: str) -> None:
        # Bulk-archive every active entity in the category (soft-delete,
        # recoverable). `purge_all` scopes the prune to the whole category;
        # entities in the other tier are untouched.
        self._client.call_tool("perseus_vault_prune", {
            "category": category,
            "purge_all": True,
        })

    def delete_memory(self, memory_id: str, memory_type: Optional[str] = None) -> bool:
        # Accept both the short hint ("short") and the MemoryProtocol value
        # ("short_term"); anything else targets the long-term tier.
        if memory_type in ("short", "short_term"):
            cats = [self._st_cat]
        elif memory_type in ("long", "long_term"):
            cats = [self._lt_cat]
        else:
            # Type unspecified: try both tiers.
            cats = [self._st_cat, self._lt_cat]
        ok = False
        for c in cats:
            try:
                res = self._client.call_tool("perseus_vault_forget", {
                    "category": c, "key": memory_id, "reason": "PraisonAI delete_memory",
                })
            except Exception:
                continue
            # Only report success if the vault actually archived the entity;
            # a missing key / wrong category yields archived == 0. A non-dict
            # response is ambiguous and is NOT treated as success (avoids
            # reporting a delete that may never have happened).
            if isinstance(res, dict) and res.get("archived", 0):
                ok = True
        return ok

    def delete_memories(self, memory_ids: List[str]) -> int:
        return sum(1 for mid in memory_ids if self.delete_memory(mid))

    def get_context(self, query: Optional[str] = None, **kwargs) -> str:
        """Return a pre-formatted markdown context block for prompt injection."""
        args: Dict[str, Any] = {}
        if query:
            args["query"] = query
        if "limit" in kwargs:
            args["limit"] = kwargs["limit"]
        res = self._client.call_tool("perseus_vault_context", args)
        if isinstance(res, str):
            return res
        if isinstance(res, dict):
            # perseus_vault_context returns a structured block; the rendered
            # prompt-ready text lives under "markdown".
            return res.get("markdown") or res.get("context") or res.get("text") or ""
        return ""

    def close(self) -> None:
        self._client.close()
