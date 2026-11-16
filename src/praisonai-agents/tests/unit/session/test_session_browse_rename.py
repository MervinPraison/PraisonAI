import json

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore
from praisonaiagents.tools.session_tools import SessionTools


@pytest.mark.parametrize('store_type', [DefaultSessionStore, SqliteSessionStore, SqliteTranscriptStore])
def test_browse_uses_saved_rename_and_retains_fallbacks(tmp_path, store_type):
    store = store_type(session_dir=str(tmp_path))
    assert store.add_message('renamed', 'user', 'unique search phrase')
    assert store.set_agent_info('renamed', agent_name='Agent')
    assert store.rename_session('renamed', '  Fix auth bug  ')
    assert store.add_message('plain', 'user', 'ordinary conversation')
    listings = {item['session_id']: item for item in store.list_sessions()}
    assert listings['renamed']['title'] == 'Fix auth bug'
    assert listings['plain']['title'] is None
    tools = SessionTools(store=store)

    browse = json.loads(tools.session_search())
    assert browse['success']
    titles = {item['session_id']: item['title'] for item in browse['results']}
    assert titles['renamed'] == 'Fix auth bug'
    assert titles['plain'] == 'plain'
    search = json.loads(tools.session_search(query='unique search phrase'))
    assert search['success']
    assert search['results'][0]['title'] == 'Fix auth bug'

    assert store.rename_session('renamed', ' ')
    titles = {item['session_id']: item['title'] for item in json.loads(tools.session_search())['results']}
    assert titles['renamed'] == 'Agent'
