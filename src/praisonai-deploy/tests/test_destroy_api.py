"""
Unit tests for cross-platform local API server destroy.
"""
from unittest.mock import patch, Mock


def _make_deploy(port=8015):
    from praisonai_deploy.main import Deploy
    from praisonai_deploy.models import DeployConfig, DeployType, APIConfig

    config = DeployConfig(type=DeployType.API, api=APIConfig(port=port))
    return Deploy(config, agents_file="agents.yaml")


def test_find_pids_on_port_unix_lsof():
    """Unix path uses lsof and parses PIDs."""
    from praisonai_deploy.main import Deploy

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "12345\n67890\n"

    with patch('sys.platform', 'linux'), \
            patch('subprocess.run', return_value=mock_result) as mock_run:
        pids = Deploy._find_pids_on_port(8015)

    assert pids == [12345, 67890]
    assert mock_run.call_args[0][0][0] == 'lsof'


def test_find_pids_on_port_windows_netstat():
    """Windows path parses netstat -ano LISTENING lines."""
    from praisonai_deploy.main import Deploy

    netstat_output = (
        "\n  Proto  Local Address          Foreign Address        State           PID\n"
        "  TCP    0.0.0.0:8015           0.0.0.0:0              LISTENING       4321\n"
        "  TCP    0.0.0.0:9999           0.0.0.0:0              LISTENING       1111\n"
    )
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = netstat_output

    with patch('sys.platform', 'win32'), \
            patch('subprocess.run', return_value=mock_result) as mock_run:
        pids = Deploy._find_pids_on_port(8015)

    assert pids == [4321]
    assert mock_run.call_args[0][0][0] == 'netstat'


def test_find_pids_on_port_lsof_missing():
    """Missing lsof/netstat binary yields empty list, not an exception."""
    from praisonai_deploy.main import Deploy

    with patch('sys.platform', 'linux'), \
            patch('subprocess.run', side_effect=FileNotFoundError()):
        pids = Deploy._find_pids_on_port(8015)

    assert pids == []


def test_kill_pid_unix():
    """Unix kill uses os.kill with SIGTERM."""
    from praisonai_deploy.main import Deploy

    with patch('sys.platform', 'linux'), patch('os.kill') as mock_kill:
        assert Deploy._kill_pid(12345) is True
        mock_kill.assert_called_once()


def test_kill_pid_windows():
    """Windows kill uses taskkill /F."""
    from praisonai_deploy.main import Deploy

    with patch('sys.platform', 'win32'), \
            patch('subprocess.run') as mock_run:
        assert Deploy._kill_pid(12345) is True
        assert mock_run.call_args[0][0][0] == 'taskkill'


def test_destroy_api_windows_stops_server():
    """Full destroy on Windows finds and kills the PID."""
    deploy = _make_deploy(8015)

    with patch.object(deploy, '_find_pids_on_port', return_value=[4321]), \
            patch.object(deploy, '_kill_pid', return_value=True) as mock_kill:
        result = deploy._destroy_api()

    assert result.success is True
    assert result.resources_deleted == ["process:4321"]
    mock_kill.assert_called_once_with(4321)


def test_destroy_api_no_server_running():
    """Destroy when nothing is listening succeeds with no resources."""
    deploy = _make_deploy(8015)

    with patch.object(deploy, '_find_pids_on_port', return_value=[]):
        result = deploy._destroy_api()

    assert result.success is True
    assert result.resources_deleted == []
    assert "No API server running" in result.message
