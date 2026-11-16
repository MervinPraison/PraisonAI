"""Tests for praisonaiagents._version.get_version (issue #6418)."""

import warnings
from unittest import mock

from praisonaiagents import _version


def _fake_file(tmp_path, pyproject_text=None):
    pkg = tmp_path / "praisonaiagents"
    pkg.mkdir()
    if pyproject_text is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject_text)
    return str(pkg / "_version.py")


def test_source_tree_pyproject_is_used(tmp_path):
    fake = _fake_file(tmp_path, '[project]\nname = "praisonaiagents"\nversion = "9.9.9"\n')
    with mock.patch.object(_version, "__file__", fake):
        assert _version.get_version() == "9.9.9"


def test_foreign_pyproject_in_site_packages_ignored(tmp_path):
    fake = _fake_file(tmp_path, '[project]\nname = "other"\ndynamic = ["version"]\n')
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", return_value="1.2.3"), \
            warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _version.get_version() == "1.2.3"


def test_foreign_static_version_not_used(tmp_path):
    fake = _fake_file(tmp_path, '[project]\nname = "other"\nversion = "0.0.1"\n')
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", return_value="1.2.3"):
        assert _version.get_version() == "1.2.3"


def test_wheel_layout_without_pyproject_uses_metadata(tmp_path):
    fake = _fake_file(tmp_path)
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", return_value="4.5.6"), \
            warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _version.get_version() == "4.5.6"


def test_unknown_when_nothing_available(tmp_path):
    from importlib.metadata import PackageNotFoundError

    fake = _fake_file(tmp_path)
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", side_effect=PackageNotFoundError):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert _version.get_version() == "unknown"


def test_name_outside_project_table_not_trusted(tmp_path):
    fake = _fake_file(
        tmp_path,
        '[project]\nname = "other"\nversion = "0.0.1"\n\n'
        '[tool.something]\nname = "praisonaiagents"\nversion = "6.6.6"\n',
    )
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", return_value="1.2.3"):
        assert _version.get_version() == "1.2.3"


def test_undecodable_pyproject_falls_back_to_metadata(tmp_path):
    fake = _fake_file(tmp_path)
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\xfa not utf-8")
    with mock.patch.object(_version, "__file__", fake), \
            mock.patch("importlib.metadata.version", return_value="7.8.9"):
        assert _version.get_version() == "7.8.9"
