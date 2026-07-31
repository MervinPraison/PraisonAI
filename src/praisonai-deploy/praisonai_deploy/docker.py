"""
Docker deployment functionality.
"""
import os
import re
import subprocess
import json
from typing import Optional, Dict, Tuple
from pathlib import Path
from .models import DockerConfig, DeployResult, DeployStatus, DestroyResult, ServiceState

# Environment variables commonly required inside deployed containers.
RUNTIME_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "PRAISONAI_API_TOKEN",
)


def resolve_docker_paths(agents_file: str) -> Tuple[str, str, Path]:
    """Return build context directory, agents basename, and resolved agents path."""
    agents_path = Path(agents_file).resolve()
    return str(agents_path.parent), agents_path.name, agents_path


def docker_container_name(config: DockerConfig) -> str:
    """Stable, Docker-valid container name for a Docker deploy config.

    Docker container names must match ``[a-zA-Z0-9][a-zA-Z0-9_.-]*``; any
    disallowed character (e.g. ``/`` in ``team/app``) is replaced with ``-``.
    """
    raw = f"{config.image_name}-{config.tag}"
    name = re.sub(r'[^a-zA-Z0-9_.-]', '-', raw)
    return name.lstrip('-._') or 'praisonai-app'


def collect_runtime_env_vars(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Collect host env vars to pass through to containers."""
    env_vars = {key: os.environ[key] for key in RUNTIME_ENV_KEYS if os.environ.get(key)}
    if extra:
        env_vars.update(extra)
    return env_vars


def generate_dockerfile(agents_file: str, config: Optional[DockerConfig] = None) -> str:
    """
    Generate Dockerfile for agents.
    
    Args:
        agents_file: Path to agents.yaml file
        config: Docker configuration
        
    Returns:
        Dockerfile content as string
    """
    if config is None:
        config = DockerConfig()

    agents_basename = Path(agents_file).name
    
    # Build expose statements
    expose_lines = "\n".join([f"EXPOSE {port}" for port in config.expose])
    
    dockerfile = f"""FROM {config.base_image}

WORKDIR /app

# Copy application files (use basename so absolute host paths work in build context)
COPY {agents_basename} /app/{agents_basename}
COPY api_server.py /app/api_server.py

# Install dependencies
RUN pip install --no-cache-dir praisonai flask flask-cors gunicorn

# Expose ports
{expose_lines}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{config.expose[0]}/health')" || exit 1

# Run the application
CMD ["gunicorn", "-b", "0.0.0.0:{config.expose[0]}", "-w", "1", "api_server:app"]
"""
    
    return dockerfile


def check_docker_installed() -> bool:
    """
    Check if Docker is installed and available.
    
    Returns:
        True if Docker is available, False otherwise
    """
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def build_docker_image(config: DockerConfig, build_context: str = ".") -> DeployResult:
    """
    Build Docker image.
    
    Args:
        config: Docker configuration
        build_context: Build context directory
        
    Returns:
        DeployResult with build information
    """
    try:
        if not check_docker_installed():
            return DeployResult(
                success=False,
                message="Docker not installed",
                error="Docker is required for Docker deployment"
            )
        
        # Build image tag
        image_tag = f"{config.image_name}:{config.tag}"
        if config.registry:
            image_tag = f"{config.registry}/{image_tag}"
        
        # Build command
        cmd = ['docker', 'build', '-t', image_tag]
        
        # Add build args if provided
        if config.build_args:
            for key, value in config.build_args.items():
                cmd.extend(['--build-arg', f"{key}={value}"])
        
        cmd.append(build_context)
        
        print(f"🐳 Building Docker image: {image_tag}")
        
        # Run build
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return DeployResult(
                success=True,
                message=f"Docker image built successfully: {image_tag}",
                metadata={"image": image_tag, "tag": config.tag}
            )
        else:
            return DeployResult(
                success=False,
                message="Docker build failed",
                error=result.stderr
            )
    
    except Exception as e:
        return DeployResult(
            success=False,
            message="Docker build failed",
            error=str(e)
        )


def run_docker_container(
    config: DockerConfig,
    env_vars: Optional[Dict[str, str]] = None,
    detached: bool = True,
    replace_existing: bool = True,
) -> DeployResult:
    """
    Run Docker container.
    
    Args:
        config: Docker configuration
        env_vars: Environment variables to pass to container
        detached: Run in detached mode
        
    Returns:
        DeployResult with container information
    """
    try:
        # Build image tag
        image_tag = f"{config.image_name}:{config.tag}"
        if config.registry:
            image_tag = f"{config.registry}/{image_tag}"
        
        # Build run command
        cmd = ['docker', 'run']
        
        if detached:
            cmd.append('-d')
        
        # Add port mappings
        for port in config.expose:
            cmd.extend(['-p', f"{port}:{port}"])
        
        # Add environment variables
        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(['-e', f"{key}={value}"])
        
        # Add container name
        container_name = docker_container_name(config)
        if replace_existing:
            subprocess.run(
                ['docker', 'rm', '-f', container_name],
                capture_output=True,
                timeout=30,
            )
        cmd.extend(['--name', container_name])
        
        cmd.append(image_tag)
        
        print(f"🚀 Starting Docker container: {container_name}")
        
        # Run container
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            container_id = result.stdout.strip()
            url = f"http://localhost:{config.expose[0]}"
            
            return DeployResult(
                success=True,
                message=f"Container started successfully: {container_name}",
                url=url,
                metadata={
                    "container_id": container_id,
                    "container_name": container_name,
                    "image": image_tag
                }
            )
        else:
            return DeployResult(
                success=False,
                message="Failed to start container",
                error=result.stderr
            )
    
    except Exception as e:
        return DeployResult(
            success=False,
            message="Failed to start container",
            error=str(e)
        )


def push_docker_image(config: DockerConfig) -> DeployResult:
    """
    Push Docker image to registry.
    
    Args:
        config: Docker configuration
        
    Returns:
        DeployResult with push information
    """
    try:
        if not config.registry:
            return DeployResult(
                success=False,
                message="No registry specified",
                error="Registry URL required for push operation"
            )
        
        # Build image tag
        image_tag = f"{config.registry}/{config.image_name}:{config.tag}"
        
        print(f"📤 Pushing Docker image to registry: {image_tag}")
        
        # Push image
        result = subprocess.run(
            ['docker', 'push', image_tag],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return DeployResult(
                success=True,
                message=f"Image pushed successfully: {image_tag}",
                metadata={"image": image_tag}
            )
        else:
            return DeployResult(
                success=False,
                message="Docker push failed",
                error=result.stderr
            )
    
    except Exception as e:
        return DeployResult(
            success=False,
            message="Docker push failed",
            error=str(e)
        )


def stop_docker_container(container_id: str) -> bool:
    """
    Stop Docker container.
    
    Args:
        container_id: Container ID or name
        
    Returns:
        True if stopped successfully, False otherwise
    """
    try:
        result = subprocess.run(
            ['docker', 'stop', container_id],
            capture_output=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def save_dockerfile(
    agents_file: str,
    config: Optional[DockerConfig] = None,
    output_path: Optional[str] = None,
):
    """
    Save generated Dockerfile to file.
    
    Args:
        agents_file: Path to agents.yaml file (basename used in COPY instructions)
        config: Docker configuration
        output_path: Path to save Dockerfile (defaults to agents file directory)
    """
    build_context, agents_basename, _ = resolve_docker_paths(agents_file)
    dockerfile_content = generate_dockerfile(agents_basename, config)

    if output_path is None:
        output_path = str(Path(build_context) / "Dockerfile")

    path = Path(output_path)
    with open(path, 'w') as f:
        f.write(dockerfile_content)


def prepare_docker_build_context(agents_file: str, api_server_code: str) -> str:
    """Write api_server.py next to the agents file; return the build context path."""
    build_context, _, agents_path = resolve_docker_paths(agents_file)
    if not agents_path.exists():
        raise FileNotFoundError(f"Agents file not found: {agents_file}")
    api_server_path = Path(build_context) / "api_server.py"
    with open(api_server_path, 'w', encoding='utf-8') as f:
        f.write(api_server_code)
    return build_context


def get_docker_container_status(config: DockerConfig) -> DeployStatus:
    """
    Get status of a Docker container.
    
    Args:
        config: Docker configuration
        
    Returns:
        DeployStatus with container information
    """
    try:
        container_name = docker_container_name(config)
        
        result = subprocess.run(
            ['docker', 'inspect', container_name, '--format', '{{json .}}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return DeployStatus(
                state=ServiceState.NOT_FOUND,
                message=f"Container not found: {container_name}",
                service_name=container_name,
                provider="docker"
            )
        
        data = json.loads(result.stdout)
        state_data = data.get('State', {})
        running = state_data.get('Running', False)
        status_str = state_data.get('Status', 'unknown')
        
        # Map Docker status to ServiceState
        if running:
            state = ServiceState.RUNNING
        elif status_str == 'exited':
            state = ServiceState.STOPPED
        elif status_str == 'created':
            state = ServiceState.PENDING
        elif status_str == 'dead':
            state = ServiceState.FAILED
        else:
            state = ServiceState.UNKNOWN
        
        # Get port mapping
        ports = data.get('NetworkSettings', {}).get('Ports', {})
        url = None
        if ports and config.expose:
            port_key = f"{config.expose[0]}/tcp"
            if port_key in ports and ports[port_key]:
                host_port = ports[port_key][0].get('HostPort')
                if host_port:
                    url = f"http://localhost:{host_port}"
        
        return DeployStatus(
            state=state,
            url=url,
            message=f"Status: {status_str}",
            service_name=container_name,
            provider="docker",
            healthy=running,
            instances_running=1 if running else 0,
            instances_desired=1,
            created_at=data.get('Created'),
            metadata={
                "container_id": data.get('Id', '')[:12],
                "image": data.get('Config', {}).get('Image'),
                "status": status_str,
                "started_at": state_data.get('StartedAt'),
                "finished_at": state_data.get('FinishedAt')
            }
        )
        
    except Exception as e:
        return DeployStatus(
            state=ServiceState.UNKNOWN,
            message=f"Failed to get status: {e}",
            service_name=config.image_name,
            provider="docker"
        )


def remove_docker_container(config: DockerConfig, force: bool = False) -> DestroyResult:
    """
    Remove Docker container and optionally the image.
    
    Args:
        config: Docker configuration
        force: Force removal and also remove image
        
    Returns:
        DestroyResult with removal information
    """
    try:
        container_name = docker_container_name(config)
        deleted_resources = []
        
        # Stop container first
        print(f"🛑 Stopping container: {container_name}")
        subprocess.run(
            ['docker', 'stop', container_name],
            capture_output=True,
            timeout=30
        )
        
        # Remove container
        print(f"🗑️ Removing container: {container_name}")
        result = subprocess.run(
            ['docker', 'rm', container_name] + (['-f'] if force else []),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            deleted_resources.append(f"container:{container_name}")
        else:
            return DestroyResult(
                success=False,
                message="Failed to remove container",
                error=result.stderr,
                resources_deleted=deleted_resources
            )
        
        # Optionally remove image
        if force:
            image_tag = f"{config.image_name}:{config.tag}"
            print(f"🗑️ Removing image: {image_tag}")
            img_result = subprocess.run(
                ['docker', 'rmi', image_tag, '-f'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if img_result.returncode == 0:
                deleted_resources.append(f"image:{image_tag}")
        
        return DestroyResult(
            success=True,
            message="Successfully removed Docker container",
            resources_deleted=deleted_resources,
            metadata={"container_name": container_name}
        )
        
    except Exception as e:
        return DestroyResult(
            success=False,
            message="Failed to remove Docker resources",
            error=str(e)
        )
