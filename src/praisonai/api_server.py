"""
Auto-generated API server for PraisonAI agents.

Security defaults
-----------------

Authentication is enabled by default and the server binds to localhost.
To run unauthenticated (e.g. inside a trusted private network behind an
authenticating proxy) set ``PRAISONAI_API_AUTH=disabled`` explicitly.

Configuration via environment variables:

* ``PRAISONAI_API_AUTH``   - ``enabled`` (default) or ``disabled``.
* ``PRAISONAI_API_TOKEN``  - bearer token required when auth is enabled.
                             If unset, a random token is generated at
                             startup and printed to stderr.
* ``PRAISONAI_API_HOST``   - bind host (default ``127.0.0.1``).
* ``PRAISONAI_API_PORT``   - bind port (default ``8080``).
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from praisonai import PraisonAI
import os
import secrets
import sys

app = Flask(__name__)

# CORS configuration
CORS(app)

# Authentication is ON by default. Operators can opt out explicitly with
# ``PRAISONAI_API_AUTH=disabled`` if they front the server with another
# authenticator. When enabled, a bearer token is required: either set
# ``PRAISONAI_API_TOKEN`` or accept the random one generated at startup.
AUTH_ENABLED = os.environ.get("PRAISONAI_API_AUTH", "enabled").strip().lower() != "disabled"
AUTH_TOKEN = os.environ.get("PRAISONAI_API_TOKEN") or None

if AUTH_ENABLED and not AUTH_TOKEN:
    AUTH_TOKEN = secrets.token_urlsafe(32)
    # Print to stderr so it shows up in logs but never in HTTP responses.
    print(
        f"[praisonai-api] generated API token (set PRAISONAI_API_TOKEN to override): {AUTH_TOKEN}",
        file=sys.stderr,
        flush=True,
    )


def check_auth():
    """Check authentication if enabled.

    Uses a constant-time comparison to avoid timing oracles that could
    let an attacker recover the bearer token byte-by-byte.
    """
    if not AUTH_ENABLED:
        return True

    if not AUTH_TOKEN:
        # Fail closed if auth is enabled but no token was configured.
        return False

    token = request.headers.get('Authorization', '').replace('Bearer ', '', 1)
    return secrets.compare_digest(token, AUTH_TOKEN)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "praisonai-api"})

@app.route('/chat', methods=['POST'])
def chat():
    """Chat endpoint for agent interaction."""
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "Message required"}), 400
    
    try:
        praisonai = PraisonAI(agent_file="agents.yaml")
        result = praisonai.run()
        
        return jsonify({
            "response": result,
            "status": "success"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route('/agents', methods=['GET'])
def list_agents():
    """List available agents."""
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    return jsonify({
        "agents": ["default"],
        "agent_file": "agents.yaml"
    })

if __name__ == '__main__':
    # Bind to localhost by default. Operators that need to expose the
    # server externally must opt in via ``PRAISONAI_API_HOST=0.0.0.0`` and
    # should always pair that with authentication or a fronting proxy.
    
    # Parse host with empty string fallback
    host = os.environ.get("PRAISONAI_API_HOST") or "127.0.0.1"
    
    # Parse port with error handling
    raw_port = os.environ.get("PRAISONAI_API_PORT") or "8080"
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 8080
        print(f"[praisonai-api] invalid PRAISONAI_API_PORT={raw_port!r}; using 8080", file=sys.stderr)
    
    app.run(host=host, port=port, debug=False)
