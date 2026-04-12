"""Tests for cloud compute adapters: E2B, Modal, Daytona.

Unit tests (no API calls): test protocol conformance, config, init.
Integration tests (require credentials): marked with provider-specific markers.
"""

import asyncio
import os
import pytest


# --------------------------------------------------------------------------- #
# Unit tests — no API calls required
# --------------------------------------------------------------------------- #

class TestE2BComputeUnit:
    def test_importable(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        assert E2BCompute is not None

    def test_provider_name(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        compute = E2BCompute(api_key="test")
        assert compute.provider_name == "e2b"

    def test_is_available_with_key(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        compute = E2BCompute(api_key="test-key")
        assert compute.is_available is True

    def test_is_available_without_key(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        old = os.environ.pop("E2B_API_KEY", None)
        try:
            compute = E2BCompute(api_key="")
            assert compute.is_available is False
        finally:
            if old:
                os.environ["E2B_API_KEY"] = old

    def test_protocol_methods_exist(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        compute = E2BCompute(api_key="test")
        for method in ["provision", "shutdown", "get_status", "execute",
                       "upload_file", "download_file", "list_instances"]:
            assert hasattr(compute, method), f"Missing method: {method}"

    def test_execute_nonexistent_instance(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        compute = E2BCompute(api_key="test")
        result = asyncio.run(compute.execute("nonexistent", "echo hello"))
        assert result["exit_code"] == -1


class TestModalComputeUnit:
    def test_importable(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        assert ModalCompute is not None

    def test_provider_name(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        compute = ModalCompute()
        assert compute.provider_name == "modal"

    def test_is_available(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        compute = ModalCompute()
        result = compute.is_available
        assert isinstance(result, bool)

    def test_protocol_methods_exist(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        compute = ModalCompute()
        for method in ["provision", "shutdown", "get_status", "execute",
                       "upload_file", "download_file", "list_instances"]:
            assert hasattr(compute, method), f"Missing method: {method}"

    def test_execute_nonexistent_instance(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        compute = ModalCompute()
        result = asyncio.run(compute.execute("nonexistent", "echo hello"))
        assert result["exit_code"] == -1


class TestDaytonaComputeUnit:
    def test_importable(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        assert DaytonaCompute is not None

    def test_provider_name(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        compute = DaytonaCompute(api_key="test")
        assert compute.provider_name == "daytona"

    def test_is_available_with_key(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        compute = DaytonaCompute(api_key="test-key")
        assert compute.is_available is True

    def test_is_available_without_key(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        old = os.environ.pop("DAYTONA_API_KEY", None)
        try:
            compute = DaytonaCompute(api_key="")
            assert compute.is_available is False
        finally:
            if old:
                os.environ["DAYTONA_API_KEY"] = old

    def test_protocol_methods_exist(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        compute = DaytonaCompute(api_key="test")
        for method in ["provision", "shutdown", "get_status", "execute",
                       "upload_file", "download_file", "list_instances"]:
            assert hasattr(compute, method), f"Missing method: {method}"

    def test_execute_nonexistent_instance(self):
        from praisonai.integrations.compute.daytona import DaytonaCompute
        compute = DaytonaCompute(api_key="test")
        result = asyncio.run(compute.execute("nonexistent", "echo hello"))
        assert result["exit_code"] == -1


class TestComputeExports:
    def test_all_adapters_from_init(self):
        from praisonai.integrations.compute import (
            DockerCompute,
            LocalCompute,
            DaytonaCompute,
            E2BCompute,
            ModalCompute,
            FlyioCompute,
        )
        assert DockerCompute is not None
        assert LocalCompute is not None
        assert DaytonaCompute is not None
        assert E2BCompute is not None
        assert ModalCompute is not None
        assert FlyioCompute is not None


# --------------------------------------------------------------------------- #
# Integration tests — require live credentials
# --------------------------------------------------------------------------- #

class TestE2BComputeIntegration:
    @pytest.fixture(autouse=True)
    def skip_without_key(self):
        if not os.environ.get("E2B_API_KEY"):
            pytest.skip("E2B_API_KEY not set")

    def test_provision_execute_shutdown(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        from praisonaiagents.managed.protocols import ComputeConfig, InstanceStatus

        compute = E2BCompute()
        config = ComputeConfig(
            working_dir="/home/user",
            idle_timeout_s=120,
            env={"TEST_VAR": "hello_e2b"},
        )

        info = asyncio.run(compute.provision(config))
        assert info.status == InstanceStatus.RUNNING
        assert info.provider == "e2b"
        assert info.instance_id.startswith("e2b_")

        result = asyncio.run(compute.execute(info.instance_id, "echo $TEST_VAR"))
        assert result["exit_code"] == 0
        assert "hello_e2b" in result["stdout"]

        result2 = asyncio.run(compute.execute(info.instance_id, "python3 -c 'print(2+2)'"))
        assert result2["exit_code"] == 0
        assert "4" in result2["stdout"]

        status = asyncio.run(compute.get_status(info.instance_id))
        assert status.status == InstanceStatus.RUNNING

        instances = asyncio.run(compute.list_instances())
        assert len(instances) >= 1

        asyncio.run(compute.shutdown(info.instance_id))
        status2 = asyncio.run(compute.get_status(info.instance_id))
        assert status2.status == InstanceStatus.STOPPED

    def test_pip_install(self):
        from praisonai.integrations.compute.e2b import E2BCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = E2BCompute()
        config = ComputeConfig(
            packages={"pip": ["requests"]},
            idle_timeout_s=120,
        )

        info = asyncio.run(compute.provision(config))
        result = asyncio.run(compute.execute(
            info.instance_id,
            "python3 -c 'import requests; print(requests.__version__)'",
        ))
        assert result["exit_code"] == 0
        assert result["stdout"].strip()  # Should print version

        asyncio.run(compute.shutdown(info.instance_id))


class TestModalComputeIntegration:
    @pytest.fixture(autouse=True)
    def skip_without_config(self):
        config_path = os.path.expanduser("~/.modal.toml")
        if not os.path.exists(config_path) and not os.environ.get("MODAL_TOKEN_ID"):
            pytest.skip("Modal not configured")

    def test_provision_execute_shutdown(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        from praisonaiagents.managed.protocols import ComputeConfig, InstanceStatus

        compute = ModalCompute(app_name="praisonai-test")
        config = ComputeConfig(
            idle_timeout_s=120,
            env={"TEST_VAR": "hello_modal"},
        )

        info = asyncio.run(compute.provision(config))
        assert info.status == InstanceStatus.RUNNING
        assert info.provider == "modal"
        assert info.instance_id.startswith("modal_")

        result = asyncio.run(compute.execute(info.instance_id, "echo $TEST_VAR"))
        assert result["exit_code"] == 0
        assert "hello_modal" in result["stdout"]

        result2 = asyncio.run(compute.execute(info.instance_id, "python3 -c 'print(2+2)'"))
        assert result2["exit_code"] == 0
        assert "4" in result2["stdout"]

        instances = asyncio.run(compute.list_instances())
        assert len(instances) >= 1

        asyncio.run(compute.shutdown(info.instance_id))

    def test_pip_install_via_image(self):
        from praisonai.integrations.compute.modal_compute import ModalCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = ModalCompute(app_name="praisonai-test")
        config = ComputeConfig(
            packages={"pip": ["requests"]},
            idle_timeout_s=120,
        )

        info = asyncio.run(compute.provision(config))
        result = asyncio.run(compute.execute(
            info.instance_id,
            "python3 -c 'import requests; print(requests.__version__)'",
        ))
        assert result["exit_code"] == 0
        assert result["stdout"].strip()

        asyncio.run(compute.shutdown(info.instance_id))


class TestDockerComputeIntegration:
    @pytest.fixture(autouse=True)
    def skip_without_docker(self):
        from praisonai.integrations.compute.docker import DockerCompute
        compute = DockerCompute()
        if not compute.is_available:
            pytest.skip("Docker not available")

    def test_provision_execute_shutdown(self):
        from praisonai.integrations.compute.docker import DockerCompute
        from praisonaiagents.managed.protocols import ComputeConfig, InstanceStatus

        compute = DockerCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            cpu=1,
            memory_mb=512,
            env={"TEST_VAR": "hello_docker"},
            auto_shutdown=True,
        )

        info = asyncio.run(compute.provision(config))
        assert info.status == InstanceStatus.RUNNING
        assert info.provider == "docker"

        result = asyncio.run(compute.execute(info.instance_id, "echo $TEST_VAR"))
        assert result["exit_code"] == 0
        assert "hello_docker" in result["stdout"]

        result2 = asyncio.run(compute.execute(info.instance_id, "python3 -c 'print(2+2)'"))
        assert result2["exit_code"] == 0
        assert "4" in result2["stdout"]

        asyncio.run(compute.shutdown(info.instance_id))

    def test_file_upload_download(self):
        import tempfile
        from praisonai.integrations.compute.docker import DockerCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = DockerCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            auto_shutdown=True,
        )
        info = asyncio.run(compute.provision(config))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content from host")
            local_path = f.name

        ok = asyncio.run(compute.upload_file(info.instance_id, local_path, "/workspace/test.txt"))
        assert ok is True

        dl_path = local_path + ".download"
        ok2 = asyncio.run(compute.download_file(info.instance_id, "/workspace/test.txt", dl_path))
        assert ok2 is True

        with open(dl_path) as f:
            assert f.read() == "test content from host"

        os.unlink(local_path)
        os.unlink(dl_path)
        asyncio.run(compute.shutdown(info.instance_id))

    def test_pip_install(self):
        from praisonai.integrations.compute.docker import DockerCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = DockerCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            packages={"pip": ["requests"]},
            auto_shutdown=True,
        )
        info = asyncio.run(compute.provision(config))

        result = asyncio.run(compute.execute(
            info.instance_id,
            "python3 -c 'import requests; print(requests.__version__)'",
        ))
        assert result["exit_code"] == 0
        assert result["stdout"].strip()

        asyncio.run(compute.shutdown(info.instance_id))
