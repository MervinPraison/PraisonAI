"""Desktop knowledge / RAG: index folders and retrieve context for chat."""

from __future__ import annotations

import json
import os
import pathlib
import re
import threading
import time

CONFIG_NAME = "knowledge.json"
_TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".html", ".htm", ".yaml", ".yml", ".log",
}
_MAX_FILE_BYTES = 500_000
_MAX_FALLBACK_CHARS = 48_000


class KnowledgeSupervisor:
    """Index local paths with praisonaiagents and serve retrieval for chat."""

    def __init__(self, home: pathlib.Path, *, model: str = "gpt-4o-mini"):
        self.home = home
        self.model = model
        self.root = home / "knowledge"
        self.config_path = self.root / CONFIG_NAME
        self._lock = threading.RLock()
        self._agent = None
        self._last_error: str | None = None
        self.root.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> dict:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_config(self, cfg: dict) -> None:
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        os.replace(tmp, self.config_path)

    def _normalize_paths(self, paths: list) -> list[str]:
        out: list[str] = []
        for raw in paths or []:
            p = pathlib.Path(str(raw).strip()).expanduser()
            if not p.is_dir():
                raise ValueError(f"not a folder: {p}")
            out.append(str(p.resolve()))
        if not out:
            raise ValueError("add at least one folder path")
        return out

    def status(self) -> dict:
        with self._lock:
            cfg = self._load_config()
            paths = cfg.get("paths") or []
            return {
                "paths": paths,
                "indexed_at": cfg.get("indexed_at"),
                "ready": self._agent is not None and bool(paths),
                "error": self._last_error,
            }

    def configure(self, paths: list) -> dict:
        with self._lock:
            normalized = self._normalize_paths(paths)
            cfg = self._load_config()
            cfg["paths"] = normalized
            cfg.pop("indexed_at", None)
            self._save_config(cfg)
            self._agent = None
            self._last_error = None
            return self.status()

    def reindex(self) -> dict:
        with self._lock:
            cfg = self._load_config()
            paths = cfg.get("paths") or []
            if not paths:
                raise ValueError("configure folder paths before indexing")
            self._last_error = None
            try:
                from praisonaiagents import Agent

                agent = Agent(
                    name="DesktopKnowledge",
                    instructions="Retrieve relevant facts from indexed documents.",
                    knowledge=list(paths),
                    llm=self.model,
                )
                agent._ensure_knowledge_processed()
                self._agent = agent
                cfg["indexed_at"] = int(time.time())
                self._save_config(cfg)
            except Exception as exc:  # noqa: BLE001
                self._agent = None
                self._last_error = str(exc)
                raise RuntimeError(self._last_error) from exc
            return self.status()

    def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        cfg = self._load_config()
        if not cfg.get("paths"):
            raise ValueError("no knowledge folders configured")
        self.reindex()

    def _collect_text_files(self, paths: list[str]) -> list[tuple[str, str]]:
        """Read small text-like files under configured folders."""
        out: list[tuple[str, str]] = []
        for raw in paths:
            root = pathlib.Path(raw)
            if not root.is_dir():
                continue
            for fp in root.rglob("*"):
                if not fp.is_file():
                    continue
                suf = fp.suffix.lower()
                if suf not in _TEXT_SUFFIXES:
                    continue
                try:
                    if fp.stat().st_size > _MAX_FILE_BYTES:
                        continue
                    body = fp.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
                if body:
                    out.append((str(fp.relative_to(root)), body))
        return out

    def _fallback_scan(self, query: str, paths: list[str]) -> str:
        """When vector/RAG search misses (common on tiny folders), scan disk."""
        docs = self._collect_text_files(paths)
        if not docs:
            return ""
        combined = "\n\n".join(f"[{name}]\n{body}" for name, body in docs)
        if len(combined) <= _MAX_FALLBACK_CHARS:
            return combined
        terms = {t.lower() for t in re.findall(r"\w+", query) if len(t) > 2}
        scored: list[tuple[int, str]] = []
        for name, body in docs:
            low = body.lower()
            score = sum(1 for t in terms if t in low) if terms else 1
            if score:
                scored.append((score, f"[{name}]\n{body}"))
        scored.sort(key=lambda x: -x[0])
        chunks: list[str] = []
        n = 0
        for _, block in scored:
            if n + len(block) > _MAX_FALLBACK_CHARS:
                break
            chunks.append(block)
            n += len(block) + 2
        return "\n\n".join(chunks)

    def query(self, text: str, *, max_chars: int = 12_000) -> str:
        with self._lock:
            self._ensure_agent()
            assert self._agent is not None
            ctx, _ = self._agent._get_knowledge_context(text, use_rag=True)
            if not ctx:
                ctx, _ = self._agent._get_knowledge_context(text, use_rag=False)
            if not ctx:
                cfg = self._load_config()
                ctx = self._fallback_scan(text, cfg.get("paths") or [])
            if not ctx:
                return ""
            ctx = str(ctx)
            if len(ctx) > max_chars:
                ctx = ctx[:max_chars] + "\n…"
            return ctx
