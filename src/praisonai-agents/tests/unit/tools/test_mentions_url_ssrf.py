"""@url mentions must not fetch loopback targets."""

from praisonaiagents.tools.mentions import MentionsParser


def test_url_mention_blocks_loopback():
    parser = MentionsParser()
    result = parser._process_url_mention("http://127.0.0.1:8765/")
    assert result is not None
    assert "Blocked" in result
