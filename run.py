"""Start the AgentOS frontend dev server on port 5000."""
import os
import subprocess
import sys

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(__file__), "frontend"))
    subprocess.run(
        ["npm", "run", "dev"],
        env={**os.environ},
    )
