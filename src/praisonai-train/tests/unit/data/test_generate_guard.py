"""Tests for the in-loop continuation guard and per-row provenance stamping.

Network is stubbed (``_call`` is monkeypatched, or a fake recipe is used) so these
run offline and deterministically. They exercise two additive generator features:

* ``should_continue`` guard: halts generation cleanly once the predicate returns
  False after ``sponsor_check_rows`` completions, and never halts while True; and
* provenance stamping: emitted rows carry ``model``/``task_type``/``topic`` when
  those are available, and omit them when they are not.
"""
from praisonai_train.data import generate as gen_mod
from praisonai_train.data.generate import generate_dataset


def _cfg(n, **extra):
    cfg = {"endpoint": "http://x", "api_key": "k", "deployment": "d", "num_examples": n,
           "concurrency": 1, "stop_file": "/nonexistent/stop"}
    cfg.update(extra)
    return cfg


def _fake_call(cfg, spec):
    # Unique instruction per spec so dedup keeps every row.
    return {"instruction": spec["user"], "input": "", "output": "ஒரு முழுமையான தமிழ் பதில் இங்கே."}


# --- Feature 1: the continuation guard ---------------------------------------

def test_guard_halts_generation_after_n_rows(monkeypatch):
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    calls = {"n": 0}

    def should_continue():
        # True on the first check, False on the second -> halt at 2*check_every.
        calls["n"] += 1
        return calls["n"] < 2

    # check_every=3: guard runs at done==3 (True) and done==6 (False -> halt).
    rows = list(generate_dataset(_cfg(20, sponsor_check_rows=3),
                                 should_continue=should_continue))

    assert calls["n"] == 2                 # guard was polled exactly twice
    # Halted at the second poll (done==6); the run stopped well short of 20 rows.
    assert len(rows) <= 6
    assert len(rows) < 20


def test_guard_does_not_halt_while_true(monkeypatch):
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    polls = {"n": 0}

    def should_continue():
        polls["n"] += 1
        return True                        # always healthy

    n = 12
    rows = list(generate_dataset(_cfg(n, sponsor_check_rows=3),
                                 should_continue=should_continue))

    assert len(rows) == n                  # nothing halted; all rows emitted
    assert polls["n"] >= 1                  # guard was actually exercised


def test_no_guard_by_default(monkeypatch):
    # Backward compatible: no should_continue and no subscription_id => unguarded.
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    rows = list(generate_dataset(_cfg(5)))
    assert len(rows) == 5


def test_guard_resolved_from_subscription_id(monkeypatch):
    # When no callback is passed but a subscription id is present, the built-in
    # Azure sponsorship guard is wired in. Stub the factory to observe wiring
    # without touching the network / az CLI.
    monkeypatch.setattr(gen_mod, "_call", _fake_call)
    built = {"sub": None, "polls": 0}

    def fake_factory(sub):
        built["sub"] = sub

        def _check():
            built["polls"] += 1
            return False                   # not sponsored -> halt
        return _check

    monkeypatch.setattr(gen_mod, "azure_sponsorship_guard", fake_factory)
    rows = list(generate_dataset(_cfg(20, subscription_id="sub-123",
                                      sponsor_check_rows=2)))

    assert built["sub"] == "sub-123"        # factory built from cfg subscription_id
    assert built["polls"] >= 1              # guard was polled
    assert len(rows) < 20                   # halted before completing


def test_azure_sponsorship_guard_fails_open(monkeypatch):
    # The built-in guard must return True (fail-OPEN) when the az CLI is missing /
    # errors, so a flaky check never halts a healthy run.
    guard = gen_mod.azure_sponsorship_guard("sub-xyz")

    def boom(*a, **k):
        raise FileNotFoundError("az not installed")

    monkeypatch.setattr("subprocess.run", boom)
    assert guard() is True


# --- Feature 2: per-row provenance stamping ----------------------------------

class _FakeRecipe:
    """A recipe whose specs carry task_type/topic, to verify pass-through."""
    name = "fake"

    def prompts(self, n, start=0):
        return [{"system": "s", "user": f"u{i}",
                 "task_type": "translation", "topic": f"topic-{i}"}
                for i in range(start, start + n)]


class _BareRecipe:
    """A recipe whose specs have no task_type/topic metadata."""
    name = "bare"

    def prompts(self, n, start=0):
        return [{"system": "s", "user": f"u{i}"} for i in range(start, start + n)]


def _patch_http(monkeypatch, payload_output="ஒரு முழுமையான தமிழ் பதில் இங்கே."):
    """Stub urllib so the real ``_call`` (and thus its stamping) runs offline."""
    import json as _json

    class _Resp:
        def __init__(self, user):
            self._user = user

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            content = _json.dumps({"instruction": self._user, "input": "",
                                   "output": payload_output})
            return _json.dumps(
                {"choices": [{"message": {"content": content}}]}).encode()

    # urllib.request.urlopen is called with a Request built from the spec's user
    # message; decode it to echo a unique instruction back.
    def fake_urlopen(req, timeout=0):
        body = _json.loads(req.data.decode())
        return _Resp(body["messages"][1]["content"])

    monkeypatch.setattr(gen_mod.urllib.request, "urlopen", fake_urlopen)


def test_rows_carry_provenance_when_available(monkeypatch):
    monkeypatch.setattr(gen_mod, "resolve", lambda name: _FakeRecipe())
    _patch_http(monkeypatch)
    rows = list(generate_dataset(_cfg(3, deployment="gpt-teacher")))

    assert len(rows) == 3
    for r in rows:
        assert r["model"] == "gpt-teacher"           # deployment stamped
        assert r["task_type"] == "translation"        # passed through from spec
        assert r["topic"].startswith("topic-")        # passed through from spec
        # Core fields remain intact.
        assert set(["instruction", "input", "output"]).issubset(r)


def test_rows_omit_provenance_when_absent(monkeypatch):
    monkeypatch.setattr(gen_mod, "resolve", lambda name: _BareRecipe())
    _patch_http(monkeypatch)
    # deployment is required to build the request, so model is always present;
    # task_type/topic must be OMITTED (not stamped as empty) when the spec lacks them.
    rows = list(generate_dataset(_cfg(3, deployment="gpt-teacher")))

    assert len(rows) == 3
    for r in rows:
        assert r["model"] == "gpt-teacher"
        assert "task_type" not in r
        assert "topic" not in r
