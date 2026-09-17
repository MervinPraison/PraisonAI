"""Knowledge sources can live in cloud object storage.

Knowledge could only read local disk. detect_source_kind() already classified
s3:// and gs:// as URLs, but nothing fetched them -- so a bucket path was handed
to an HTTP fetcher that cannot speak those schemes.
"""
import os
import sys
import types
import pytest

from praisonaiagents.knowledge.cloud import (
    CloudSourceError,
    fetch_cloud_source,
    is_cloud_source,
    parse_cloud_uri,
)


class TestRecognition:
    @pytest.mark.parametrize("uri", [
        "s3://bucket/doc.pdf",
        "gs://bucket/doc.pdf",
        "az://container/doc.pdf",
        "https://acct.blob.core.windows.net/container/doc.pdf",
    ])
    def test_cloud_uris_are_recognised(self, uri):
        assert is_cloud_source(uri) is True

    @pytest.mark.parametrize("uri", [
        "/local/doc.pdf", "doc.pdf", "https://example.com/doc.pdf", "", None,
    ])
    def test_control_non_cloud_sources_are_not_claimed(self, uri):
        """Control: an ordinary URL must still go to the web fetcher."""
        assert is_cloud_source(uri) is False

    def test_control_blob_text_in_query_is_not_an_azure_host(self):
        """A normal https URL that merely mentions the Azure host in its query
        must not be misrouted to the cloud branch."""
        assert is_cloud_source(
            "https://example.com/doc.pdf?x=.blob.core.windows.net"
        ) is False


class TestParsing:
    def test_s3_splits_into_bucket_and_key(self):
        assert parse_cloud_uri("s3://my-bucket/docs/a.pdf") == ("s3", "my-bucket", "docs/a.pdf")

    def test_gs_splits_the_same_way(self):
        assert parse_cloud_uri("gs://b/k.pdf") == ("gcs", "b", "k.pdf")

    def test_an_azure_blob_url_splits_into_container_and_blob(self):
        provider, container, key = parse_cloud_uri(
            "https://acct.blob.core.windows.net/docs/handbook.pdf"
        )
        assert (provider, container, key) == ("azure", "docs", "handbook.pdf")

    def test_an_unsupported_scheme_is_refused_by_name(self):
        with pytest.raises(CloudSourceError, match="Not a supported cloud source"):
            parse_cloud_uri("ftp://host/file.pdf")

    def test_percent_encoded_object_names_are_decoded(self):
        """SDKs expect the literal object name, so %20 must become a space."""
        _provider, _container, key = parse_cloud_uri(
            "https://acct.blob.core.windows.net/docs/handbook%20v2.pdf"
        )
        assert key == "handbook v2.pdf"

    def test_s3_key_is_also_decoded(self):
        assert parse_cloud_uri("s3://b/a%20b.pdf") == ("s3", "b", "a b.pdf")


class TestFetching:
    def test_it_downloads_and_keeps_the_extension(self, tmp_path, monkeypatch):
        """The readers dispatch on extension, so an extension-less temp file
        would make a PDF be read as plain text."""
        fake = types.ModuleType("boto3")

        class _Client:
            def download_file(self, bucket, key, dest):
                with open(dest, "w") as handle:
                    handle.write("downloaded")

        fake.client = lambda *a, **k: _Client()
        monkeypatch.setitem(sys.modules, "boto3", fake)

        path = fetch_cloud_source("s3://bucket/docs/handbook.pdf", dest_dir=str(tmp_path))
        assert path.endswith("handbook.pdf")
        assert open(path).read() == "downloaded"

    def test_a_missing_sdk_names_the_pip_package(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "boto3", None)
        with pytest.raises(CloudSourceError, match="pip install boto3"):
            fetch_cloud_source("s3://bucket/a.pdf")

    def test_a_uri_without_an_object_is_refused(self):
        with pytest.raises(CloudSourceError, match="container and an object"):
            fetch_cloud_source("s3://bucket-only")

    def test_a_provider_error_is_reported_not_swallowed(self, tmp_path, monkeypatch):
        """A failed download must not look like an empty document."""
        fake = types.ModuleType("boto3")

        class _Client:
            def download_file(self, *a, **k):
                raise RuntimeError("AccessDenied")

        fake.client = lambda *a, **k: _Client()
        monkeypatch.setitem(sys.modules, "boto3", fake)

        with pytest.raises(CloudSourceError, match="AccessDenied"):
            fetch_cloud_source("s3://bucket/a.pdf", dest_dir=str(tmp_path))

    def test_a_silent_no_op_download_is_caught(self, tmp_path, monkeypatch):
        """If an SDK reports success but writes nothing, say so."""
        fake = types.ModuleType("boto3")

        class _Client:
            def download_file(self, *a, **k):
                return None

        fake.client = lambda *a, **k: _Client()
        monkeypatch.setitem(sys.modules, "boto3", fake)

        with pytest.raises(CloudSourceError, match="wrote no file"):
            fetch_cloud_source("s3://bucket/a.pdf", dest_dir=str(tmp_path))

    def test_azure_streams_into_the_file_and_binds_the_url_account(
        self, tmp_path, monkeypatch
    ):
        """Azure downloads must stream (readinto) rather than buffer the whole
        blob, and address the account named by the URL, not the env account."""
        seen = {}

        class _Downloader:
            def readinto(self, handle):
                handle.write(b"streamed")

        class _BlobClient:
            def download_blob(self):
                return _Downloader()

        class _BSC:
            def __init__(self, account_url=None, credential=None):
                seen["account_url"] = account_url

            @classmethod
            def from_connection_string(cls, conn):
                seen["from_conn"] = conn
                return cls()

            def get_blob_client(self, container, key):
                seen["container"], seen["key"] = container, key
                return _BlobClient()

        blob_mod = types.ModuleType("azure.storage.blob")
        blob_mod.BlobServiceClient = _BSC
        azure_pkg = types.ModuleType("azure")
        storage_pkg = types.ModuleType("azure.storage")
        monkeypatch.setitem(sys.modules, "azure", azure_pkg)
        monkeypatch.setitem(sys.modules, "azure.storage", storage_pkg)
        monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_mod)
        monkeypatch.setitem(sys.modules, "azure.identity", None)
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

        path = fetch_cloud_source(
            "https://accta.blob.core.windows.net/docs/handbook.pdf",
            dest_dir=str(tmp_path),
        )
        assert open(path, "rb").read() == b"streamed"
        assert seen["account_url"] == "https://accta.blob.core.windows.net"
        assert (seen["container"], seen["key"]) == ("docs", "handbook.pdf")
