"""Desktop `/search` delegates to the ranked FTS5 session store (Issue #4701).

The engine's Ctrl/Cmd-K search used to load every chat JSON and do a substring
``in`` scan that stopped at the first hit per chat — no ranking, no snippets.
It now delegates to the library's ``SqliteSessionStore`` (FTS5/bm25). These
tests index three chats, query a term present in two, and assert both come back
ranked with a snippet. The mutation test (reverting to the substring scan)
would fail the ranking assertion because a substring scan returns matches in
directory order, not by relevance.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest

AGENTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "praisonai-agents")
)
if AGENTS not in sys.path:
    sys.path.insert(0, AGENTS)


class SearchRankingTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-search-")
        os.environ["PRAISONAI_DESKTOP_HOME"] = self.home
        os.environ["XDG_DATA_HOME"] = self.home
        # Import the engine fresh so DATA_DIR/CHATS_DIR pick up the temp home.
        for mod in [m for m in list(sys.modules) if m == "server"]:
            del sys.modules[mod]
        sys.path.insert(0, os.path.dirname(__file__))
        self.server = importlib.import_module("server")

    def _write_chat(self, cid, title, messages):
        self.server.CHATS_DIR.mkdir(parents=True, exist_ok=True)
        chat = {
            "id": cid,
            "title": title,
            "updated": 1,
            "messages": messages,
        }
        (self.server.CHATS_DIR / f"{cid}.json").write_text(json.dumps(chat))

    def test_returns_both_matches_ranked_with_snippet(self):
        # Two chats mention "migration"; "zeta" heavily, "alpha" once. A third
        # does not. "zeta" is named so it sorts *last* alphabetically/by
        # directory order — the order the old substring scan would return —
        # so the ranking assertion only holds under real bm25 relevance.
        self.assertLess("alpha", "zeta")
        self._write_chat(
            "alpha",
            "Alpha",
            [
                {"role": "user", "content": "one mention of migration here"},
            ],
        )
        self._write_chat(
            "zeta",
            "Zeta",
            [
                {"role": "user", "content": "we need a billing migration migration migration plan"},
                {"role": "assistant", "content": "the migration is scheduled"},
            ],
        )
        self._write_chat(
            "gamma",
            "Gamma",
            [
                {"role": "user", "content": "totally unrelated content about weather"},
            ],
        )

        hits = self.server._search_chats("migration")
        ids = [h["id"] for h in hits]

        # Both matching chats returned; the non-matching one excluded.
        self.assertIn("alpha", ids)
        self.assertIn("zeta", ids)
        self.assertNotIn("gamma", ids)

        # Every hit carries a snippet containing the query term.
        for h in hits:
            self.assertTrue(h["snippet"])
            self.assertIn("migration", h["snippet"].lower())

        # Ranking: the denser-match chat ranks first even though it sorts last
        # by name. A substring scan returns matches in directory order, so this
        # assertion fails if search reverts to the substring scan (mutation).
        self.assertEqual(ids[0], "zeta")

    def test_empty_query_returns_no_hits(self):
        self._write_chat("a", "A", [{"role": "user", "content": "hello"}])
        self.assertEqual(self.server._search_chats(""), [])


if __name__ == "__main__":
    unittest.main()
