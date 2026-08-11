"""
Main Deploy class for unified deployment interface.
"""
from typing import Dict, Any
from .models import DeployConfig, DeployResult, DeployType, DeployStatus, DestroyResult, ServiceState
from .schema import validate_agents_yaml
from .api import start_api_server, generate_api_server_code
from .docker import (
    build_docker_image, run_docker_container, push_docker_image, save_dockerfile,
    get_docker_container_status, remove_docker_container,
    prepare_docker_build_context, collect_runtime_env_vars, resolve_docker_paths,
)
from .providers import get_provider


class Deploy:
    """
    Unified deployment interface for PraisonAI agents.
    
    Supports:
    - API server deployment (local/production)
    - Docker containerization
    - Cloud deployment (AWS, Azure, GCP)
    
    Examples:
        # From YAML
        deploy = Deploy.from_yaml("agents.yaml")
        result = deploy.deploy()
        
        # Programmatic
        from praisonai_deploy import Deploy, DeployConfig, DeployType
        
        config = DeployConfig(type=DeployType.API)
        deploy = Deploy(config, agents_file="agents.yaml")
        result = deploy.deploy()
    """
    
    def __init__(self, config: DeployConfig, agents_file: str = "agents.yaml"):
        """
        Initialize Deploy with configuration.
        
        Args:
            config: Deployment configuration
            agents_file: Path to agents.yaml file
        """
        self.config = config
        self.agents_file = agents_file
    
    @classmethod
    def from_yaml(cls, agents_file: str = "agents.yaml") -> 'Deploy':
        """
        Create Deploy instance from agents.yaml file.
        
        Args:
            agents_file: Path to agents.yaml file
            
        Returns:
            Deploy instance
            
        Raises:
            ValueError: If no deploy configuration found in YAML
        """
        config = validate_agents_yaml(agents_file)
        
        if config is None:
            raise ValueError(f"No deploy configuration found in {agents_file}")
        
        return cls(config, agents_file)
    
    def deploy(self, background: bool = False) -> DeployResult:
        """
        Execute deployment based on configuration.
        
        Args:
            background: Run in background mode (for API deployments)
            
        Returns:
            DeployResult with deployment information
        """
        if self.config.type == DeployType.API:
            return self._deploy_api(background)
        elif self.config.type == DeployType.DOCKER:
            return self._deploy_docker()
        elif self.config.type == DeployType.CLOUD:
            return self._deploy_cloud()
        else:
            return DeployResult(
                success=False,
                message=f"Unsupported deployment type: {self.config.type}",
                error="Invalid deployment type"
            )
    
    def _deploy_api(self, background: bool = False) -> DeployResult:
        """Deploy as API server."""
        return start_api_server(
            self.agents_file,
            self.config.api,
            background=background
        )
    
    def _deploy_docker(self) -> DeployResult:
        """Deploy as Docker container."""
        from .models import APIConfig

        _, agents_basename, _ = resolve_docker_paths(self.agents_file)
        docker_cfg = self.config.docker
        if docker_cfg is None:
            raise ValueError(
                "Docker deployment requires a 'docker' section in the deploy configuration"
            )

        api_config = self.config.api or APIConfig(
            host="0.0.0.0",
            port=docker_cfg.expose[0] if docker_cfg.expose else 8005,
        )

        save_dockerfile(self.agents_file, docker_cfg)
        api_code = generate_api_server_code(agents_basename, api_config)
        build_context = prepare_docker_build_context(self.agents_file, api_code)

        build_result = build_docker_image(docker_cfg, build_context)

        if not build_result.success:
            return build_result

        if docker_cfg.push and docker_cfg.registry:
            push_result = push_docker_image(docker_cfg)
            if not push_result.success:
                return push_result

        auth_env = None
        if self.config.api and not self.config.api.auth_enabled:
            auth_env = {"PRAISONAI_API_AUTH": "disabled"}
        env_vars = collect_runtime_env_vars(extra=auth_env)

        return run_docker_container(docker_cfg, env_vars=env_vars, replace_existing=True)
    
    def _deploy_cloud(self) -> DeployResult:
        """Deploy to cloud provider."""
        provider = get_provider(self.config.cloud)
        return provider.deploy()
    
    def plan(self) -> Dict[str, Any]:
        """
        Generate deployment plan without executing.
        
        Returns:
            Dictionary with planned deployment configuration
        """
        if self.config.type == DeployType.API:
            return {
                "type": "api",
                "host": self.config.api.host,
                "port": self.config.api.port,
                "workers": self.config.api.workers,
                "agents_file": self.agents_file
            }
        elif self.config.type == DeployType.DOCKER:
            return {
                "type": "docker",
                "image": f"{self.config.docker.image_name}:{self.config.docker.tag}",
                "registry": self.config.docker.registry,
                "push": self.config.docker.push,
                "ports": self.config.docker.expose
            }
        elif self.config.type == DeployType.CLOUD:
            provider = get_provider(self.config.cloud)
            return provider.plan()
        else:
            return {"error": "Invalid deployment type"}
    
    def doctor(self):
        """
        Run health checks for deployment.
        
        Returns:
            DoctorReport with check results
        """
        from .doctor import run_local_checks, run_all_checks, DoctorReport
        
        if self.config.type == DeployType.API:
            return run_local_checks(
                port=self.config.api.port,
                agents_file=self.agents_file
            )
        elif self.config.type == DeployType.DOCKER:
            from .doctor import check_docker_available, DoctorReport
            checks = run_local_checks(agents_file=self.agents_file).checks
            checks.append(check_docker_available())
            return DoctorReport(checks=checks)
        elif self.config.type == DeployType.CLOUD:
            provider = get_provider(self.config.cloud)
            return provider.doctor()
        else:
            return run_all_checks(self.agents_file)
    
    def status(self) -> DeployStatus:
        """
        Get current deployment status.
        
        Returns:
            DeployStatus with current state and information
        """
        if self.config.type == DeployType.API:
            return self._status_api()
        elif self.config.type == DeployType.DOCKER:
            return self._status_docker()
        elif self.config.type == DeployType.CLOUD:
            return self._status_cloud()
        else:
            return DeployStatus(
                state=ServiceState.UNKNOWN,
                message=f"Unsupported deployment type: {self.config.type}"
            )
    
    def _status_api(self) -> DeployStatus:
        """Get status of local API server."""
        import socket
        port = self.config.api.port if self.config.api else 8005
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result == 0:
                return DeployStatus(
                    state=ServiceState.RUNNING,
                    url=f"http://127.0.0.1:{port}",
                    message=f"API server running on port {port}",
                    service_name="praisonai-api",
                    provider="api",
                    healthy=True,
                    instances_running=1,
                    instances_desired=1
                )
            else:
                return DeployStatus(
                    state=ServiceState.STOPPED,
                    message=f"No service running on port {port}",
                    service_name="praisonai-api",
                    provider="api",
                    healthy=False,
                    instances_running=0,
                    instances_desired=1
                )
        except Exception as e:
            return DeployStatus(
                state=ServiceState.UNKNOWN,
                message=f"Failed to check status: {e}",
                service_name="praisonai-api",
                provider="api"
            )
    
    def _status_docker(self) -> DeployStatus:
        """Get status of Docker container."""
        return get_docker_container_status(self.config.docker)
    
    def _status_cloud(self) -> DeployStatus:
        """Get status of cloud deployment."""
        provider = get_provider(self.config.cloud)
        return provider.status()
    
    def destroy(self, force: bool = False) -> DestroyResult:
        """
        Destroy/delete the deployment.
        
        Args:
            force: Force deletion without confirmation
            
        Returns:
            DestroyResult with deletion information
        """
        if self.config.type == DeployType.API:
            return self._destroy_api()
        elif self.config.type == DeployType.DOCKER:
            return self._destroy_docker(force)
        elif self.config.type == DeployType.CLOUD:
            return self._destroy_cloud(force)
        else:
            return DestroyResult(
                success=False,
                message=f"Unsupported deployment type: {self.config.type}",
                error="Invalid deployment type"
            )
    
    @staticmethod
    def _find_pids_on_port(port: int) -> list:
        """Find PIDs listening on a port (cross-platform).

        Uses ``netstat -ano`` on Windows and ``lsof`` on Unix-like systems.
        """
        import subprocess
        import sys

        pids = []
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    needle = f":{port}"
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if len(parts) < 5 or "LISTENING" not in line:
                            continue
                        local_addr = parts[1]
                        if local_addr.endswith(needle):
                            try:
                                pids.append(int(parts[-1]))
                            except ValueError:
                                pass
            else:
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    for pid in result.stdout.strip().split('\n'):
                        try:
                            pids.append(int(pid))
                        except ValueError:
                            pass
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        return list(dict.fromkeys(pids))

    @staticmethod
    def _kill_pid(pid: int) -> bool:
        """Terminate a process by PID (cross-platform)."""
        import subprocess
        import signal
        import sys
        import os

        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ['taskkill', '/PID', str(pid), '/F'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            os.kill(pid, signal.SIGTERM)
            return True
        except (ProcessLookupError, FileNotFoundError, OSError, subprocess.SubprocessError):
            return False

    def _destroy_api(self) -> DestroyResult:
        """Stop local API server (cross-platform)."""
        port = self.config.api.port if self.config.api else 8005

        try:
            pids = self._find_pids_on_port(port)

            if not pids:
                return DestroyResult(
                    success=True,
                    message=f"No API server running on port {port}",
                    resources_deleted=[]
                )

            deleted_resources = []
            failed_pids = []
            for pid in pids:
                if self._kill_pid(pid):
                    deleted_resources.append(f"process:{pid}")
                else:
                    failed_pids.append(pid)

            if failed_pids:
                return DestroyResult(
                    success=False,
                    message=f"Failed to stop API server on port {port}",
                    resources_deleted=deleted_resources,
                    error=f"Could not stop processes: {', '.join(map(str, failed_pids))}"
                )

            return DestroyResult(
                success=True,
                message=f"Stopped API server on port {port}",
                resources_deleted=deleted_resources
            )
        except Exception as e:
            return DestroyResult(
                success=False,
                message="Failed to stop API server",
                error=str(e)
            )
    
    def _destroy_docker(self, force: bool = False) -> DestroyResult:
        """Remove Docker container."""
        return remove_docker_container(self.config.docker, force)
    
    def _destroy_cloud(self, force: bool = False) -> DestroyResult:
        """Destroy cloud deployment."""
        provider = get_provider(self.config.cloud)
        return provider.destroy(force)
