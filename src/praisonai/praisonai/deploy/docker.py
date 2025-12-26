"""
Docker deployment functionality.
"""
import subprocess
import os
from typing import Optional, Dict
from pathlib import Path
from .models import DockerConfig, DeployResult


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
    
    # Build expose statements
    expose_lines = "\n".join([f"EXPOSE {port}" for port in config.expose])
    
    dockerfile = f"""FROM {config.base_image}

WORKDIR /app

# Copy application files
COPY {agents_file} /app/{agents_file}
COPY . /app/

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
    detached: bool = True
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
        container_name = f"{config.image_name}-{config.tag}".replace(':', '-')
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


def save_dockerfile(agents_file: str, config: Optional[DockerConfig] = None, output_path: str = "Dockerfile"):
    """
    Save generated Dockerfile to file.
    
    Args:
        agents_file: Path to agents.yaml file
        config: Docker configuration
        output_path: Path to save Dockerfile
    """
    dockerfile_content = generate_dockerfile(agents_file, config)
    
    path = Path(output_path)
    with open(path, 'w') as f:
        f.write(dockerfile_content)
