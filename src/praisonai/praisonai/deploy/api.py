"""
API server deployment functionality.
"""
import subprocess
import os
import signal
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
    
    code = f'''"""
Auto-generated API server for PraisonAI agents.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from praisonai import PraisonAI
import os

app = Flask(__name__)

# CORS configuration
{"CORS(app)" if config.cors_enabled else "# CORS disabled"}

# Authentication
AUTH_ENABLED = {config.auth_enabled}
AUTH_TOKEN = {repr(config.auth_token)}

def check_auth():
    """Check authentication if enabled."""
    if not AUTH_ENABLED:
        return True
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    return token == AUTH_TOKEN

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
        praisonai = PraisonAI(agent_file="{agents_file}")
        result = praisonai.run()
        
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
        "agent_file": "{agents_file}"
    }})

if __name__ == '__main__':
    app.run(
        host='{config.host}',
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
        
        # Write to temporary file
        server_file = "api_server.py"
        with open(server_file, 'w') as f:
            f.write(server_code)
        
        # Install flask and flask-cors if needed
        try:
            subprocess.run(
                ['pip', 'install', '-q', 'flask', 'flask-cors'],
                check=False,
                capture_output=True
            )
        except Exception:
            pass
        
        # Start server
        if background:
            process = subprocess.Popen(
                ['python', server_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
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
            
            process = subprocess.Popen(['python', server_file])
            
            return DeployResult(
                success=True,
                message=f"API server running at {url}",
                url=url,
                metadata={"pid": process.pid, "server_file": server_file}
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
