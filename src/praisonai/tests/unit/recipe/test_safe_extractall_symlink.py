"""Regression tests for GHSA-9q28-ghcr-c4x3:
Symlink-extraction bypass of _safe_extractall writes outside dest_dir.
"""
import io
import tarfile

import pytest

from praisonai.recipe.registry import RegistryError, _safe_extractall


@pytest.fixture()
def tmp_dirs(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    yield dest, outside


def _make_tar(members):
    """Build an in-memory tar and return an open TarFile."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for m in members:
            tf.addfile(m[0], m[1] if len(m) > 1 else None)
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


def test_clean_archive_extracts_ok(tmp_dirs):
    dest, _ = tmp_dirs
    payload = b"hello"
    info = tarfile.TarInfo("subdir/file.txt")
    info.size = len(payload)
    with _make_tar([(info, io.BytesIO(payload))]) as tf:
        _safe_extractall(tf, dest)
    assert (dest / "subdir" / "file.txt").read_bytes() == payload


def test_symlink_absolute_target_rejected(tmp_dirs):
    dest, outside = tmp_dirs
    sym = tarfile.TarInfo("escape")
    sym.type = tarfile.SYMTYPE
    sym.linkname = str(outside)
    with _make_tar([(sym,)]) as tf:
        with pytest.raises(RegistryError, match="Refusing to extract link"):
            _safe_extractall(tf, dest)


def test_symlink_relative_escaping_target_rejected(tmp_dirs):
    dest, _ = tmp_dirs
    sym = tarfile.TarInfo("sub/escape")
    sym.type = tarfile.SYMTYPE
    sym.linkname = "../../outside"
    with _make_tar([(sym,)]) as tf:
        with pytest.raises(RegistryError, match="Refusing to extract link"):
            _safe_extractall(tf, dest)


def test_hardlink_escaping_target_rejected(tmp_dirs):
    dest, _ = tmp_dirs
    lnk = tarfile.TarInfo("sub/hardlink")
    lnk.type = tarfile.LNKTYPE
    lnk.linkname = "../../etc/passwd"
    with _make_tar([(lnk,)]) as tf:
        with pytest.raises(RegistryError, match="Refusing to extract link"):
            _safe_extractall(tf, dest)


def test_symlink_within_dest_allowed(tmp_dirs):
    dest, _ = tmp_dirs
    sym = tarfile.TarInfo("link")
    sym.type = tarfile.SYMTYPE
    sym.linkname = "target.txt"
    payload = b"data"
    info = tarfile.TarInfo("target.txt")
    info.size = len(payload)
    with _make_tar([(info, io.BytesIO(payload)), (sym,)]) as tf:
        _safe_extractall(tf, dest)
