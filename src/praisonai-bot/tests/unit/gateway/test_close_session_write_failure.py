import pytest

from praisonaiagents.gateway import GatewayConfig, SessionConfig
from praisonaiagents.session import SqliteTranscriptStore
from praisonai_bot.gateway.server import GatewayMessage, WebSocketGateway


def make_gateway(tmp_path):
    config = GatewayConfig(session_config=SessionConfig(persist=True, persist_path=str(tmp_path)))
    gateway = WebSocketGateway(config=config)
    assert isinstance(gateway._session_store, SqliteTranscriptStore)
    session = gateway.create_session('agent', 'client', 'session')
    session.add_message(GatewayMessage(content='live', sender_id='user', session_id='session'))
    return gateway, session


@pytest.mark.parametrize('failure', ['false', 'exception'])
def test_failed_close_retains_active_session(tmp_path, monkeypatch, failure):
    gateway, session = make_gateway(tmp_path)
    def fail(*args, **kwargs):
        if failure == 'exception':
            raise OSError('controlled failure')
        return False
    with monkeypatch.context() as m:
        m.setattr(gateway._session_store, '_write_row', fail)
        assert gateway.close_session('session') is False
    assert gateway.get_session('session') is session
    assert session.is_active
    assert [m.content for m in session.get_messages()] == ['live']
    assert 'session' not in gateway._session_ttls


def test_successful_close_persists_inactive_snapshot(tmp_path):
    gateway, session = make_gateway(tmp_path)
    assert gateway.close_session('session') is True
    assert not session.is_active
    assert gateway.get_session('session') is None
    saved = gateway._session_store.get_session('session')
    assert saved.messages[-1].metadata['session_data']['is_active'] is False
    resumed = gateway.create_session('agent', 'client2', 'session')
    assert [m.content for m in resumed.get_messages()] == ['live']
