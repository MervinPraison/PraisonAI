"""
Tests for daemon platform detection and dispatch.

Tests that _detect_platform returns the correct backend for different platforms.
"""

import platform
import pytest
from unittest.mock import patch

from praisonai.daemon import _detect_platform, install_daemon, uninstall_daemon, get_daemon_status


def test_detect_platform_linux():
    """Test platform detection on Linux."""
    with patch('platform.system', return_value='Linux'):
        assert _detect_platform() == 'systemd'


def test_detect_platform_macos():
    """Test platform detection on macOS."""
    with patch('platform.system', return_value='Darwin'):
        assert _detect_platform() == 'launchd'


def test_detect_platform_windows():
    """Test platform detection on Windows."""
    with patch('platform.system', return_value='Windows'):
        assert _detect_platform() == 'windows'


def test_detect_platform_unknown():
    """Test platform detection on unknown OS."""
    with patch('platform.system', return_value='FreeBSD'):
        assert _detect_platform() == 'unknown'


@patch('praisonai.daemon._detect_platform', return_value='systemd')
@patch('praisonai.daemon.systemd.install')
def test_install_daemon_routes_to_systemd(mock_systemd_install, mock_detect):
    """Test that install_daemon routes to systemd on Linux."""
    mock_systemd_install.return_value = {"ok": True, "message": "Installed"}
    
    result = install_daemon(config_path="test.yaml")
    
    mock_systemd_install.assert_called_once_with(config_path="test.yaml")
    assert result["ok"] is True


@patch('praisonai.daemon._detect_platform', return_value='launchd')
@patch('praisonai.daemon.launchd.install')
def test_install_daemon_routes_to_launchd(mock_launchd_install, mock_detect):
    """Test that install_daemon routes to launchd on macOS."""
    mock_launchd_install.return_value = {"ok": True, "message": "Installed"}
    
    result = install_daemon(config_path="test.yaml")
    
    mock_launchd_install.assert_called_once_with(config_path="test.yaml")
    assert result["ok"] is True


@patch('praisonai.daemon._detect_platform', return_value='windows')
@patch('praisonai.daemon.windows.install')
def test_install_daemon_routes_to_windows(mock_windows_install, mock_detect):
    """Test that install_daemon routes to windows backend."""
    mock_windows_install.return_value = {"ok": True, "message": "Installed"}
    
    result = install_daemon(config_path="test.yaml")
    
    mock_windows_install.assert_called_once_with(config_path="test.yaml")
    assert result["ok"] is True


@patch('praisonai.daemon._detect_platform', return_value='unknown')
def test_install_daemon_unsupported_platform(mock_detect):
    """Test that install_daemon handles unsupported platforms."""
    result = install_daemon(config_path="test.yaml")
    
    assert result["ok"] is False
    assert "Unsupported platform" in result["error"]


@patch('praisonai.daemon._detect_platform', return_value='systemd')
@patch('praisonai.daemon.systemd.get_status')
def test_get_daemon_status_routes_to_systemd(mock_systemd_status, mock_detect):
    """Test that get_daemon_status routes to systemd on Linux."""
    mock_systemd_status.return_value = {"installed": True, "running": True}
    
    result = get_daemon_status()
    
    mock_systemd_status.assert_called_once()
    assert result["installed"] is True