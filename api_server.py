"""
Auto-generated API server for PraisonAI agents.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from praisonai import PraisonAI
import os

app = Flask(__name__)

# CORS configuration
CORS(app)

# Authentication
AUTH_ENABLED = False
AUTH_TOKEN = None

def check_auth():
    """Check authentication if enabled."""
    if not AUTH_ENABLED:
        return True
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    return token == AUTH_TOKEN

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
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=False
    )
