"""X-02: ``OPENAI_BASE_URL`` (the openai SDK's name) wins over legacy ``OPENAI_API_BASE``.

``OpenAIClient`` and the cached-client lookup read ``OPENAI_API_BASE`` first,
while the openai SDK, memory and the config registry treat
``OPENAI_BASE_URL`` as canonical. A stale legacy value in a shell or CI
silently redirected every call. Both names keep working; when both are set
and differ, the official one is used and a warning names both once.
"""

import logging

import pytest

from praisonaiagents.llm import openai_client as oc

OFFICIAL, LEGACY = "http://official.example/v1", "http://legacy.example/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setattr(oc, "_BOTH_BASE_URLS_WARNED", False, raising=False)


@pytest.mark.parametrize("official,legacy,expected", [
    (OFFICIAL, LEGACY, OFFICIAL),
    (None, LEGACY, LEGACY),
    (OFFICIAL, None, OFFICIAL),
    (None, None, None),
], ids=["both", "legacy_only", "official_only", "neither"])
def test_client_reads_official_name_first(monkeypatch, official, legacy, expected):
    if official:
        monkeypatch.setenv("OPENAI_BASE_URL", official)
    if legacy:
        monkeypatch.setenv("OPENAI_API_BASE", legacy)
    assert oc.OpenAIClient().base_url == expected


def test_explicit_base_url_still_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", OFFICIAL)
    monkeypatch.setenv("OPENAI_API_BASE", LEGACY)
    assert oc.OpenAIClient(base_url="http://explicit/v1").base_url == "http://explicit/v1"


def test_conflict_warns_once_naming_both(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_BASE_URL", OFFICIAL)
    monkeypatch.setenv("OPENAI_API_BASE", LEGACY)
    with caplog.at_level(logging.WARNING):
        oc.OpenAIClient()
        oc.OpenAIClient()
    hits = [r.getMessage() for r in caplog.records if "OPENAI_API_BASE" in r.getMessage()]
    assert len(hits) == 1 and OFFICIAL in hits[0] and LEGACY in hits[0]


def test_same_value_in_both_does_not_warn(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_BASE_URL", OFFICIAL)
    monkeypatch.setenv("OPENAI_API_BASE", OFFICIAL)
    with caplog.at_level(logging.WARNING):
        oc.OpenAIClient()
    assert not [r for r in caplog.records if "OPENAI_API_BASE" in r.getMessage()]
