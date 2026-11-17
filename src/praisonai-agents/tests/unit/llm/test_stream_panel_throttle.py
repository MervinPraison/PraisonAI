"""R-01: the verbose streaming panel is rebuilt at most every 100 ms, not per chunk."""

from types import SimpleNamespace

from praisonaiagents.llm import openai_client as oc


def test_panel_rebuilt_at_most_every_100ms(monkeypatch):
    clock = {"t": 0.0}  # first chunk must render even when the clock starts near zero
    monkeypatch.setattr(oc.time, "perf_counter", lambda: clock["t"])
    built, shown = [], []
    live = SimpleNamespace(update=shown.append)

    def display_fn(text, start):
        built.append(text)
        return f"panel:{text}"

    for i in range(50):  # 50 chunks within 50 ms
        oc._live_update(live, display_fn, f"t{i}", 0)
        clock["t"] += 0.001
    assert built == ["t0"]  # the first chunk renders at once, the rest wait
    clock["t"] += 0.1
    oc._live_update(live, display_fn, "t50", 0)
    assert built == ["t0", "t50"] and shown[-1] == "panel:t50"


def test_no_call_site_rebuilds_per_chunk():
    import inspect
    src = inspect.getsource(oc)
    assert "live.update(display_fn(" not in src.replace("        live.update(display_fn(text, start_time))", "")
