"""Load knowledge sources from cloud object storage.

`Knowledge` could only read local disk. `detect_source_kind()` already
classified `s3://` and `gs://` as URLs, but nothing fetched them -- so a bucket
path was handed to an HTTP fetcher that cannot speak those schemes. Anyone with
documents in a bucket had to download them by hand first.

This resolves a cloud URI to a local temporary file and hands it to the readers
that already exist, rather than reimplementing PDF/DOCX parsing per provider:

    Knowledge(sources=["s3://my-bucket/handbook.pdf"])

Supported: ``s3://`` (boto3), ``gs://`` (google-cloud-storage), and
``az://account/container/blob`` or ``https://<account>.blob.core.windows.net/...``
(azure-storage-blob).

Each SDK is optional and imported only when a URI of that scheme is used, so
installing PraisonAI does not pull three cloud SDKs. A missing SDK raises with
the exact pip command rather than failing later inside the provider.
"""

import os
import tempfile
from typing import Optional, Tuple
from urllib.parse import urlparse

__all__ = [
    "CLOUD_SCHEMES",
    "CloudSourceError",
    "is_cloud_source",
    "parse_cloud_uri",
    "fetch_cloud_source",
]

CLOUD_SCHEMES = ("s3", "gs", "gcs", "az", "abfs")


class CloudSourceError(RuntimeError):
    """Raised when a cloud source cannot be resolved."""


def is_cloud_source(source: str) -> bool:
    """True for a URI this module can fetch."""
    if not isinstance(source, str):
        return False
    scheme = urlparse(source.strip()).scheme.lower()
    if scheme in CLOUD_SCHEMES:
        return True
    return scheme in ("http", "https") and ".blob.core.windows.net" in source


def parse_cloud_uri(source: str) -> Tuple[str, str, str]:
    """Split a cloud URI into (provider, container, key)."""
    parsed = urlparse(source.strip())
    scheme = parsed.scheme.lower()

    if scheme == "s3":
        return "s3", parsed.netloc, parsed.path.lstrip("/")
    if scheme in ("gs", "gcs"):
        return "gcs", parsed.netloc, parsed.path.lstrip("/")
    if scheme in ("az", "abfs"):
        # az://container/blob -- the account comes from the connection string
        return "azure", parsed.netloc, parsed.path.lstrip("/")
    if scheme in ("http", "https") and ".blob.core.windows.net" in source:
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            raise CloudSourceError(
                f"Azure blob URL must include a container and a blob name: {source}"
            )
        return "azure", parts[0], parts[1]

    raise CloudSourceError(
        f"Not a supported cloud source: {source!r}. "
        f"Supported schemes: {', '.join(CLOUD_SCHEMES)}, or an Azure blob URL."
    )


def _missing(package: str, provider: str) -> CloudSourceError:
    return CloudSourceError(
        f"Reading {provider} sources needs the `{package}` package. "
        f"Install it with: pip install {package}"
    )


def _download_s3(bucket: str, key: str, dest: str) -> None:
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise _missing("boto3", "s3://") from exc
    boto3.client("s3").download_file(bucket, key, dest)


def _download_gcs(bucket: str, key: str, dest: str) -> None:
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:
        raise _missing("google-cloud-storage", "gs://") from exc
    storage.Client().bucket(bucket).blob(key).download_to_filename(dest)


def _download_azure(container: str, key: str, dest: str) -> None:
    try:
        from azure.storage.blob import BlobServiceClient  # type: ignore
    except ImportError as exc:
        raise _missing("azure-storage-blob", "Azure blob") from exc
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        raise CloudSourceError(
            "Azure blob sources need AZURE_STORAGE_CONNECTION_STRING in the environment."
        )
    client = BlobServiceClient.from_connection_string(conn)
    with open(dest, "wb") as handle:
        handle.write(client.get_blob_client(container, key).download_blob().readall())


_DOWNLOADERS = {"s3": _download_s3, "gcs": _download_gcs, "azure": _download_azure}


def fetch_cloud_source(source: str, dest_dir: Optional[str] = None) -> str:
    """Download a cloud object to a local file and return its path.

    The local name keeps the object's extension, because the readers dispatch
    on it -- a PDF fetched to an extension-less temp file would be read as plain text.
    """
    provider, container, key = parse_cloud_uri(source)
    if not container or not key:
        raise CloudSourceError(
            f"Cloud source must name a container and an object: {source!r}"
        )

    suffix = os.path.splitext(key)[1]
    directory = dest_dir or tempfile.mkdtemp(prefix="praisonai-kb-")
    os.makedirs(directory, exist_ok=True)
    dest = os.path.join(directory, os.path.basename(key) or f"object{suffix}")

    try:
        _DOWNLOADERS[provider](container, key, dest)
    except CloudSourceError:
        raise
    except Exception as exc:
        raise CloudSourceError(
            f"Could not fetch {source!r}: {type(exc).__name__}: {exc}"
        ) from exc

    if not os.path.exists(dest):
        raise CloudSourceError(f"Fetch reported success but wrote no file for {source!r}")
    return dest
