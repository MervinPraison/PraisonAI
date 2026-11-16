from threading import Event, Thread

from praisonaiagents.workflows.step_cache import FileStepCache
from praisonaiagents.workflows.workflows import AgentFlow
from praisonaiagents.utils import atomic_io


def test_clear_invalidates_another_existing_flow(tmp_path):
    path = str(tmp_path / 'shared.json')
    state = {'value': 'old'}
    calls = []

    def step(ctx):
        calls.append(state['value'])
        return state['value']

    first_cache = FileStepCache(path)
    first_flow = AgentFlow(steps=[step], cache=first_cache)
    assert first_flow.run('input', verbose=False)['output'] == 'old'

    second_cache = FileStepCache(path)
    second_flow = AgentFlow(steps=[step], cache=second_cache)
    state['value'] = 'new'
    first_cache.clear()
    assert second_flow.run('input', verbose=False)['output'] == 'new'
    assert calls == ['old', 'new']


def test_live_cache_observes_other_writes_and_external_deletion(tmp_path):
    path = tmp_path / 'shared.json'
    first = FileStepCache(path)
    second = FileStepCache(path)
    first.set('one', {'output': 'old'})
    assert second.get('one') == {'output': 'old'}
    assert len(second) == 1
    path.unlink()
    assert second.get('one') is None
    assert len(second) == 0


def test_clear_waits_for_an_inflight_shared_write(tmp_path, monkeypatch):
    path = tmp_path / 'shared.json'
    writer = FileStepCache(path)
    clearer = FileStepCache(path)
    entered, release, cleared = Event(), Event(), Event()
    write_json = atomic_io.atomic_write_json

    def delayed_write(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return write_json(*args, **kwargs)

    monkeypatch.setattr(atomic_io, 'atomic_write_json', delayed_write)
    write_thread = Thread(target=lambda: writer.set('one', {'output': 'old'}))
    clear_thread = Thread(target=lambda: (clearer.clear(), cleared.set()))
    try:
        write_thread.start()
        assert entered.wait(5)
        clear_thread.start()
        assert not cleared.wait(0.1)
    finally:
        release.set()
        write_thread.join(5)
        if clear_thread.ident is not None:
            clear_thread.join(5)
    assert not write_thread.is_alive()
    assert not clear_thread.is_alive()
    assert cleared.is_set()
    assert not path.exists()
    assert writer.get('one') is None
