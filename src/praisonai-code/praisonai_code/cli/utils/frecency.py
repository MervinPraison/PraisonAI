"""
Frecency (frequency + recency) usage store for interactive completion ranking.

Records which ``@`` paths and ``/`` commands a user accepts, per project, so
completion menus can float frequently and recently used items to the top.
An empty store yields a zero boost, leaving today's pure fuzzy order intact.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

# Upper bound on the boost added to a 0-100 fuzzy score, so usage history can
# reorder close matches but never outweighs a much better string match.
MAX_BOOST = 20
_MAX_ENTRIES = 200
# (max age in seconds, weight) — classic frecency recency buckets.
_RECENCY_BUCKETS = ((4 * 3600, 1.0), (86400, 0.7), (7 * 86400, 0.5), (30 * 86400, 0.3))
_OLD_WEIGHT = 0.1


class FrecencyStore:
    """Per-project ``{kind: {item: [count, last_used_ts]}}`` JSON store."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: Optional[Dict[str, Dict[str, list]]] = None

    @classmethod
    def for_project(cls, root_dir: Optional[str] = None) -> "FrecencyStore":
        from .project import get_project_sessions_dir
        return cls(get_project_sessions_dir(root_dir) / "frecency.json")

    def _load(self) -> Dict[str, Dict[str, list]]:
        if self._data is None:
            try:
                with open(self._path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self._data = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def boost(self, kind: str, item: str, now: Optional[float] = None) -> int:
        """Return a 0..MAX_BOOST ranking boost for ``item``."""
        try:
            count, last_used = self._load().get(kind, {})[item]
        except (KeyError, TypeError, ValueError):
            return 0
        age = (now if now is not None else time.time()) - last_used
        weight = next((w for limit, w in _RECENCY_BUCKETS if age < limit), _OLD_WEIGHT)
        return min(MAX_BOOST, round(count * weight * 4))

    def record(self, kind: str, item: str, now: Optional[float] = None) -> None:
        """Record that ``item`` was selected; best-effort persisted."""
        items = self._load().setdefault(kind, {})
        try:
            count = int(items.get(item, [0])[0])
        except (TypeError, ValueError, IndexError):
            count = 0
        items[item] = [count + 1, now if now is not None else time.time()]
        if len(items) > _MAX_ENTRIES:
            for stale in sorted(items, key=lambda k: items[k][1])[: len(items) - _MAX_ENTRIES]:
                del items[stale]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self._data), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            pass
