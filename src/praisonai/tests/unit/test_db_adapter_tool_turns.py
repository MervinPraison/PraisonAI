"""Issue #5075: the production database adapter (PraisonAIDB / SQLiteDB) must
persist assistant ``tool_calls`` and ``role="tool"`` results, and restore them
on resume, so a tool-using agent on a DB backend receives a faithful transcript
(parity with the JSON store fix in #3089).

These tests use the *real* SQLite adapter (not a MagicMock) to prove the fix
reaches the supported adapter end-to-end.
"""

import os
import tempfile
import unittest


class TestPraisonAIDBToolTurnRoundTrip(unittest.TestCase):
    def setUp(self):
        from praisonai.db.adapter import SQLiteDB

        self._path = tempfile.mktemp(suffix=".db")
        self.db = SQLiteDB(path=self._path)
        self.session_id = "sess-tool-turns"

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        if os.path.exists(self._path):
            os.remove(self._path)

    def test_assistant_tool_calls_and_tool_results_round_trip(self):
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
            }
        ]

        self.db.on_agent_start(agent_name="t", session_id=self.session_id)
        self.db.on_user_message(self.session_id, "read a.txt")
        self.db.on_assistant_message(self.session_id, "", tool_calls=tool_calls)
        self.db.on_tool_message(self.session_id, "file body", tool_call_id="call_1")
        self.db.on_agent_message(self.session_id, "Here is the file.")

        history = self.db.on_agent_start(agent_name="t", session_id=self.session_id)
        roles = [m.role for m in history]
        self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])

        # Assistant tool-call turn keeps its structured tool_calls.
        assistant = history[1]
        self.assertTrue(assistant.tool_calls)
        self.assertEqual(assistant.tool_calls[0]["id"], "call_1")
        self.assertEqual(
            assistant.tool_calls[0]["function"]["name"], "read_file"
        )

        # Tool result turn keeps its linking tool_call_id.
        tool_turn = history[2]
        self.assertEqual(tool_turn.tool_call_id, "call_1")

        # Plain turns carry no spurious tool structure.
        self.assertFalse(history[0].tool_calls)
        self.assertIsNone(history[3].tool_call_id)


if __name__ == "__main__":
    unittest.main()
