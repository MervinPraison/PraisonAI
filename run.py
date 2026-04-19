"""Start the PraisonAI Platform API server."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "praisonai-agents"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "praisonai-platform"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "praisonai_platform.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=5000,
        reload=False,
    )
