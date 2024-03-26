import subprocess
import os
from dotenv import load_dotenv

class CloudDeployer:
    def __init__(self):
        # Load environment variables from .env file or system
        load_dotenv()
        self.set_environment_variables()

    def create_dockerfile(self):
        with open("Dockerfile", "w") as file:
            file.write("FROM python:3.11-slim\n")
            file.write("WORKDIR /app\n")
            file.write("COPY . .\n")
            file.write("RUN pip install flask praisonai==0.0.17 gunicorn markdown\n")
            file.write("EXPOSE 8080\n")
            file.write('CMD ["gunicorn", "-b", "0.0.0.0:8080", "api:app"]\n')
            
    def create_api_file(self):
        with open("api.py", "w") as file:
            file.write("from flask import Flask\n")
            file.write("from praisonai import PraisonAI\n")
            file.write("import markdown\n\n")
            file.write("app = Flask(__name__)\n\n")
            file.write("def basic():\n")
            file.write("    praison_ai = PraisonAI(agent_file=\"agents.yaml\")\n")
            file.write("    return praison_ai.main()\n\n")
            file.write("@app.route('/')\n")
            file.write("def home():\n")
            file.write("    output = basic()\n")
            file.write("    html_output = markdown.markdown(output)\n")
            file.write("    return f'<html><body>{html_output}</body></html>'\n\n")
            file.write("if __name__ == \"__main__\":\n")
            file.write("    app.run(debug=True)\n")
    
    def set_environment_variables(self):
        """Sets environment variables with fallback to .env values or defaults."""
        os.environ["OPENAI_MODEL_NAME"] = os.getenv("OPENAI_MODEL_NAME", "gpt-4-turbo-preview")
        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "Enter your API key")
        os.environ["OPENAI_API_BASE"] = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    def run_commands(self):
        self.create_api_file()
        self.create_dockerfile()
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
