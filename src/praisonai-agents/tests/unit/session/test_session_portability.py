"""Tests for portable session export/import/migration (Issue #4267).

Covers the ``PortableSessionStoreProtocol`` contract and its reference
implementation on ``DefaultSessionStore`` (inherited by ``SqliteSessionStore``):
round-trip export/import, lineage-aware single export, live-field reset on
import, and the hardened import guards (caps, duplicates, malformed payloads).
"""

import tempfile

import pytest


def _make_store(tmp):
    from praisonaiagents.session.store import DefaultSessionStore

    return DefaultSessionStore(session_dir=tmp)


class TestPortableProtocol:
    def test_protocol_importable(self):
        from praisonaiagents.session import PortableSessionStoreProtocol
        assert PortableSessionStoreProtocol is not None

    def test_import_report_importable(self):
        from praisonaiagents.session import ImportReport
        rep = ImportReport(imported=2)
        assert rep.skipped_count == 0
        assert rep.as_dict()["imported"] == 2

    def test_default_store_conforms(self):
        from praisonaiagents.session import PortableSessionStoreProtocol
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            assert isinstance(store, PortableSessionStoreProtocol)

    def test_sqlite_store_conforms(self):
        from praisonaiagents.session import PortableSessionStoreProtocol
        from praisonaiagents.session.sqlite_store import SqliteSessionStore
        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteSessionStore(session_dir=tmp)
            assert isinstance(store, PortableSessionStoreProtocol)


class TestExport:
    def test_export_all_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            store.add_message("s1", "user", "hi")
            store.add_message("s2", "user", "yo")
            payload = store.export_all()
            assert payload["version"] == store.PORTABLE_VERSION
            assert len(payload["sessions"]) == 2

    def test_export_single(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            store.add_message("s1", "user", "hi")
            payload = store.export_session("s1")
            assert len(payload["sessions"]) == 1
            assert payload["sessions"][0]["session_id"] == "s1"

    def test_export_unknown_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            assert store.export_session("nope")["sessions"] == []


class TestImportRoundTrip:
    def test_roundtrip_preserves_history(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hello")
            src.add_message("s1", "assistant", "world")
            dst = _make_store(b)
            report = dst.import_sessions(src.export_all())
            assert report.imported == 1
            assert dst.session_exists("s1")
            hist = dst.get_chat_history("s1")
            assert [m["content"] for m in hist] == ["hello", "world"]

    def test_import_resets_live_fields(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            src.set_gateway_info("s1", gateway_session_id="live-1", agent_id="agentX")
            dst = _make_store(b)
            dst.import_sessions(src.export_all())
            sd = dst.get_session("s1")
            assert sd.gateway_session_id is None
            assert sd.agent_id is None

    def test_import_keep_live_fields_opt_out(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            src.set_gateway_info("s1", gateway_session_id="live-1", agent_id="agentX")
            dst = _make_store(b)
            dst.import_sessions(src.export_all(), reset_live_fields=False)
            sd = dst.get_session("s1")
            assert sd.gateway_session_id == "live-1"


class TestImportHardening:
    def test_existing_skipped_without_overwrite(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            payload = src.export_all()
            dst = _make_store(b)
            assert dst.import_sessions(payload).imported == 1
            report = dst.import_sessions(payload)
            assert report.imported == 0
            assert report.skipped_count == 1

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            payload = src.export_all()
            dst = _make_store(b)
            dst.import_sessions(payload)
            assert dst.import_sessions(payload, overwrite=True).imported == 1

    def test_max_sessions_cap(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            src.add_message("s2", "user", "yo")
            dst = _make_store(b)
            report = dst.import_sessions(src.export_all(), max_sessions=1)
            assert report.imported == 1
            assert report.skipped_count >= 1

    def test_duplicate_in_payload(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src = _make_store(a)
            src.add_message("s1", "user", "hi")
            payload = src.export_all()
            payload["sessions"].append(dict(payload["sessions"][0]))
            dst = _make_store(b)
            report = dst.import_sessions(payload)
            assert report.imported == 1
            assert any("duplicate" in s["reason"] for s in report.skipped)

    @pytest.mark.parametrize("bad", [{}, {"sessions": "x"}, {"sessions": [1, 2]}, "notadict"])
    def test_malformed_payloads(self, bad):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            report = store.import_sessions(bad)
            assert report.imported == 0
