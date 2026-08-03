"""
API server deployment functionality.
"""
import subprocess
import os
import signal
import sys
import time
from typing import Optional
from .models import APIConfig, DeployResult


def generate_api_server_code(agents_file: str, config: Optional[APIConfig] = None) -> str:
    """
    Generate API server code for serving agents.
    
    Args:
        agents_file: Path to agents.yaml file
        config: API configuration
        
    Returns:
        Python code for API server
    """
    if config is None:
        config = APIConfig()

    safe_agents_file = repr(agents_file)
    safe_host = repr(config.host)
    wrapper_pkg = "praison" + "ai"

    code = f'''"""
Auto-generated API server for PraisonAI agents.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import importlib
import os
import secrets
import sys

app = Flask(__name__)

# CORS configuration
{"CORS(app)" if config.cors_enabled else "# CORS disabled"}

# Authentication. Defaults are taken from the deploy config but can be
# overridden at runtime via env vars so operators can rotate the bearer
# token without regenerating this file.
AUTH_ENABLED = os.environ.get("PRAISONAI_API_AUTH", "{'enabled' if config.auth_enabled else 'disabled'}").strip().lower() != "disabled"
AUTH_TOKEN = os.environ.get("PRAISONAI_API_TOKEN") or {repr(config.auth_token)}

if AUTH_ENABLED and not AUTH_TOKEN:
    AUTH_TOKEN = secrets.token_urlsafe(32)
    print(
        f"[praisonai-api] generated API token (set PRAISONAI_API_TOKEN to override): {{AUTH_TOKEN}}",
        file=sys.stderr,
        flush=True,
    )

def check_auth():
    """Check authentication if enabled (constant-time compare)."""
    if not AUTH_ENABLED:
        return True
    if not AUTH_TOKEN:
        return False
    token = request.headers.get('Authorization', '').replace('Bearer ', '', 1)
    return secrets.compare_digest(token, AUTH_TOKEN)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({{"status": "ok", "service": "praisonai-api"}})

@app.route('/chat', methods=['POST'])
def chat():
    """Chat endpoint for agent interaction."""
    if not check_auth():
        return jsonify({{"error": "Unauthorized"}}), 401
    
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({{"error": "Message required"}}), 400
    
    try:
        message = data['message']
        run_fn = importlib.import_module("{wrapper_pkg}").run
        result = run_fn({safe_agents_file}, cli_config={{"topic": message}})
        
        return jsonify({{
            "response": result,
            "status": "success"
        }})
    except Exception as e:
        return jsonify({{
            "error": str(e),
            "status": "error"
        }}), 500

@app.route('/agents', methods=['GET'])
def list_agents():
    """List available agents."""
    if not check_auth():
        return jsonify({{"error": "Unauthorized"}}), 401
    
    return jsonify({{
        "agents": ["default"],
        "agent_file": {safe_agents_file}
    }})

if __name__ == '__main__':
    app.run(
        host={safe_host},
        port={config.port},
        debug={config.reload}
    )
'''
    
    return code


def start_api_server(
    agents_file: str,
    config: Optional[APIConfig] = None,
    background: bool = False
) -> DeployResult:
    """
    Start API server for agents.
    
    Args:
        agents_file: Path to agents.yaml file
        config: API configuration
        background: Run in background mode
        
    Returns:
        DeployResult with server information
    """
    if config is None:
        config = APIConfig()
    
    try:
        # Generate server code
        server_code = generate_api_server_code(agents_file, config)
        
        # Write to a private, per-invocation temp directory (mode 0700) so the
        # generated server file cannot be pre-created or replaced by another
        # local user on a shared host before it is executed.
        import tempfile
        server_dir = tempfile.mkdtemp(prefix="praisonai_api_")
        server_file = os.path.join(server_dir, "praisonai_api_server.py")
        with open(server_file, 'w') as f:
            f.write(server_code)
        
        # Install flask and flask-cors if needed. Use the same interpreter that
        # will run the server so packages land where the child process expects.
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-q', 'flask', 'flask-cors'],
                check=False,
                capture_output=True
            )
        except Exception:
            pass
        
        # Preserve the parent environment (e.g. OPENAI_API_KEY) so the generated
        # server can reach the agent runtime for /chat.
        server_env = os.environ.copy()
        
        # Start server
        if background:
            process = subprocess.Popen(
                [sys.executable, server_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                env=server_env
            )
            
            # Wait a bit to check if it started successfully
            time.sleep(2)
            
            if process.poll() is None:
                url = f"http://{config.host}:{config.port}"
                return DeployResult(
                    success=True,
                    message=f"API server started in background (PID: {process.pid})",
                    url=url,
                    metadata={"pid": process.pid, "server_file": server_file}
                )
            else:
                stderr = process.stderr.read().decode() if process.stderr else "Unknown error"
                return DeployResult(
                    success=False,
                    message="Failed to start API server",
                    error=stderr
                )
        else:
            # Run in foreground
            url = f"http://{config.host}:{config.port}"
            print(f"\n🚀 Starting API server at {url}")
            print(f"📁 Serving agents from: {agents_file}")
            print(f"🔗 Health check: {url}/health")
            print(f"💬 Chat endpoint: {url}/chat")
            print("\nPress Ctrl+C to stop the server\n")
            
            process = subprocess.Popen([sys.executable, server_file], env=server_env)
            try:
                exit_code = process.wait()
            except KeyboardInterrupt:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                exit_code = 0

            return DeployResult(
                success=exit_code in (0, None),
                message=f"API server stopped (exit code: {exit_code})",
                url=url,
                metadata={"pid": process.pid, "server_file": server_file, "exit_code": exit_code}
            )
    
    except Exception as e:
        return DeployResult(
            success=False,
            message="Failed to start API server",
            error=str(e)
        )


def check_api_health(url: str, timeout: int = 5) -> bool:
    """
    Check if API server is healthy.
    
    Args:
        url: Base URL of API server
        timeout: Request timeout in seconds
        
    Returns:
        True if healthy, False otherwise
    """
    try:
        import urllib.request
        health_url = f"{url}/health"
        
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def stop_api_server(pid: int) -> bool:
    """
    Stop API server by PID.
    
    Args:
        pid: Process ID of server
        
    Returns:
        True if stopped successfully, False otherwise
    """
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False
