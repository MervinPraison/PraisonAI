"""
Main Deploy class for unified deployment interface.
"""
from typing import Optional, Dict, Any
from pathlib import Path
from .models import DeployConfig, DeployResult, DeployType
from .schema import validate_agents_yaml
from .api import start_api_server, generate_api_server_code
from .docker import build_docker_image, run_docker_container, push_docker_image, save_dockerfile
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
        from praisonai.deploy import Deploy, DeployConfig, DeployType
        
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
        # Generate and save Dockerfile
        save_dockerfile(self.agents_file, self.config.docker)
        
        # Generate API server code
        api_code = generate_api_server_code(self.agents_file, None)
        with open("api_server.py", 'w') as f:
            f.write(api_code)
        
        # Build image
        build_result = build_docker_image(self.config.docker)
        
        if not build_result.success:
            return build_result
        
        # Push if configured
        if self.config.docker.push and self.config.docker.registry:
            push_result = push_docker_image(self.config.docker)
            if not push_result.success:
                return push_result
        
        # Run container
        return run_docker_container(self.config.docker)
    
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
