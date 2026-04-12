"""Tests for ComputeProviderProtocol and compute adapters."""

import asyncio


class TestComputeProtocol:
    def test_protocol_importable(self):
        from praisonaiagents.managed.protocols import ComputeProviderProtocol
        assert ComputeProviderProtocol is not None

    def test_compute_config_defaults(self):
        from praisonaiagents.managed.protocols import ComputeConfig
        cfg = ComputeConfig()
        assert cfg.image == "python:3.12-slim"
        assert cfg.cpu == 1
        assert cfg.memory_mb == 1024
        assert cfg.gpu is None
        assert cfg.auto_shutdown is True
        assert cfg.idle_timeout_s == 300
        assert cfg.networking == {"type": "unrestricted"}

    def test_compute_config_custom(self):
        from praisonaiagents.managed.protocols import ComputeConfig
        cfg = ComputeConfig(
            image="python:3.12",
            cpu=4,
            memory_mb=4096,
            gpu="a100-40gb",
            packages={"pip": ["pandas", "numpy"]},
            env={"API_KEY": "test"},
            auto_shutdown=True,
            idle_timeout_s=600,
        )
        assert cfg.cpu == 4
        assert cfg.gpu == "a100-40gb"
        assert cfg.packages == {"pip": ["pandas", "numpy"]}

    def test_instance_info_defaults(self):
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus
        info = InstanceInfo(instance_id="test_123")
        assert info.instance_id == "test_123"
        assert info.status == InstanceStatus.PROVISIONING
        assert info.endpoint == ""
        assert info.provider == ""

    def test_instance_status_enum(self):
        from praisonaiagents.managed.protocols import InstanceStatus
        assert InstanceStatus.PROVISIONING == "provisioning"
        assert InstanceStatus.RUNNING == "running"
        assert InstanceStatus.IDLE == "idle"
        assert InstanceStatus.STOPPING == "stopping"
        assert InstanceStatus.STOPPED == "stopped"
        assert InstanceStatus.ERROR == "error"


class TestComputeProtocolConformance:
    def test_local_compute_satisfies_protocol(self):
        from praisonaiagents.managed.protocols import ComputeProviderProtocol
        from praisonai.integrations.compute.local import LocalCompute
        compute = LocalCompute()
        # Check key interface methods exist
        assert hasattr(compute, 'provider_name')
        assert hasattr(compute, 'is_available')
        assert hasattr(compute, 'provision')
        assert hasattr(compute, 'shutdown')
        assert hasattr(compute, 'get_status')
        assert hasattr(compute, 'execute')
        assert hasattr(compute, 'upload_file')
        assert hasattr(compute, 'download_file')
        assert hasattr(compute, 'list_instances')

    def test_docker_compute_satisfies_protocol(self):
        from praisonai.integrations.compute.docker import DockerCompute
        compute = DockerCompute()
        assert hasattr(compute, 'provider_name')
        assert hasattr(compute, 'is_available')
        assert hasattr(compute, 'provision')
        assert hasattr(compute, 'shutdown')
        assert hasattr(compute, 'execute')

    def test_flyio_compute_satisfies_protocol(self):
        from praisonai.integrations.compute.flyio import FlyioCompute
        compute = FlyioCompute()
        assert hasattr(compute, 'provider_name')
        assert hasattr(compute, 'is_available')
        assert hasattr(compute, 'provision')
        assert hasattr(compute, 'shutdown')
        assert hasattr(compute, 'execute')


class TestLocalCompute:
    def test_provider_name(self):
        from praisonai.integrations.compute.local import LocalCompute
        compute = LocalCompute()
        assert compute.provider_name == "local"

    def test_is_available(self):
        from praisonai.integrations.compute.local import LocalCompute
        compute = LocalCompute()
        assert compute.is_available is True

    def test_provision_and_execute(self):
        from praisonai.integrations.compute.local import LocalCompute
        from praisonaiagents.managed.protocols import ComputeConfig, InstanceStatus

        compute = LocalCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            working_dir="/tmp",
        )

        info = asyncio.run(compute.provision(config))
        assert info.status == InstanceStatus.RUNNING
        assert info.provider == "local"
        assert info.instance_id.startswith("local_")

        result = asyncio.run(compute.execute(info.instance_id, "echo hello"))
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

        asyncio.run(compute.shutdown(info.instance_id))
        status = asyncio.run(compute.get_status(info.instance_id))
        assert status.status == InstanceStatus.STOPPED

    def test_list_instances(self):
        from praisonai.integrations.compute.local import LocalCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = LocalCompute()
        config = ComputeConfig(working_dir="/tmp")

        info = asyncio.run(compute.provision(config))
        instances = asyncio.run(compute.list_instances())
        assert len(instances) >= 1
        ids = [i.instance_id for i in instances]
        assert info.instance_id in ids

        asyncio.run(compute.shutdown(info.instance_id))

    def test_execute_with_env(self):
        from praisonai.integrations.compute.local import LocalCompute
        from praisonaiagents.managed.protocols import ComputeConfig

        compute = LocalCompute()
        config = ComputeConfig(
            working_dir="/tmp",
            env={"MY_TEST_VAR": "hello123"},
        )

        info = asyncio.run(compute.provision(config))
        result = asyncio.run(compute.execute(info.instance_id, "echo $MY_TEST_VAR"))
        assert "hello123" in result["stdout"]
        asyncio.run(compute.shutdown(info.instance_id))

    def test_execute_nonrunning_instance(self):
        from praisonai.integrations.compute.local import LocalCompute
        compute = LocalCompute()
        result = asyncio.run(compute.execute("nonexistent", "echo hello"))
        assert result["exit_code"] == -1


class TestDockerComputeInit:
    def test_provider_name(self):
        from praisonai.integrations.compute.docker import DockerCompute
        compute = DockerCompute()
        assert compute.provider_name == "docker"

    def test_is_available_without_docker(self):
        from praisonai.integrations.compute.docker import DockerCompute
        compute = DockerCompute()
        # May or may not be available depending on env
        # Just ensure it doesn't crash
        result = compute.is_available
        assert isinstance(result, bool)


class TestFlyioComputeInit:
    def test_provider_name(self):
        from praisonai.integrations.compute.flyio import FlyioCompute
        compute = FlyioCompute()
        assert compute.provider_name == "flyio"

    def test_is_available_without_token(self):
        from praisonai.integrations.compute.flyio import FlyioCompute
        import os
        old = os.environ.pop("FLY_API_TOKEN", None)
        try:
            compute = FlyioCompute(api_token="")
            assert compute.is_available is False
        finally:
            if old:
                os.environ["FLY_API_TOKEN"] = old

    def test_is_available_with_token(self):
        from praisonai.integrations.compute.flyio import FlyioCompute
        compute = FlyioCompute(api_token="test-token")
        assert compute.is_available is True


class TestExportsFromManagedInit:
    def test_protocol_exports(self):
        from praisonaiagents.managed import (
            ComputeProviderProtocol,
            ComputeConfig,
            InstanceInfo,
            InstanceStatus,
        )
        assert ComputeProviderProtocol is not None
        assert ComputeConfig is not None
        assert InstanceInfo is not None
        assert InstanceStatus is not None
