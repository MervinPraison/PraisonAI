import subprocess
import os
from dotenv import load_dotenv

class CloudDeployer:
    def __init__(self):
        # Load environment variables from .env file or system
        load_dotenv()
        self.set_environment_variables()

    def set_environment_variables(self):
        """Sets environment variables with fallback to .env values or defaults."""
        os.environ["OPENAI_MODEL_NAME"] = os.getenv("OPENAI_MODEL_NAME", "gpt-4-turbo-preview")
        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "Enter your API key")
        os.environ["OPENAI_API_BASE"] = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    def run_commands(self):
        """Runs a sequence of shell commands for deployment, continues on error."""
        commands = [
            "yes | gcloud auth configure-docker us-central1-docker.pkg.dev",
            "gcloud artifacts repositories create praisonai-repository --repository-format=docker --location=us-central1",
            "docker build --platform linux/amd64 -t gcr.io/$(gcloud config get-value project)/praisonai-app:latest .",
            "docker tag gcr.io/$(gcloud config get-value project)/praisonai-app:latest us-central1-docker.pkg.dev/$(gcloud config get-value project)/praisonai-repository/praisonai-app:latest",
            "docker push us-central1-docker.pkg.dev/$(gcloud config get-value project)/praisonai-repository/praisonai-app:latest",
            "gcloud run deploy praisonai-service --image us-central1-docker.pkg.dev/$(gcloud config get-value project)/praisonai-repository/praisonai-app:latest --platform managed --region us-central1 --allow-unauthenticated --set-env-vars OPENAI_MODEL_NAME=${OPENAI_MODEL_NAME},OPENAI_API_KEY=${OPENAI_API_KEY},OPENAI_API_BASE=${OPENAI_API_BASE}"
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"ERROR: Command '{e.cmd}' failed with exit status {e.returncode}")
                print(f"Continuing with the next command...")

# Usage
if __name__ == "__main__":
    deployer = CloudDeployer()
    deployer.run_commands()
