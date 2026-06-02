import subprocess
import os
import platform
from dotenv import load_dotenv

class CloudDeployer:
    """
    A class for deploying a cloud-based application.

    Attributes:
        None

    Methods:
        __init__(self):
            Loads environment variables from .env file or system and sets them.

    """
    def __init__(self):
        """
        Loads environment variables from .env file or system and sets them.

        Parameters:
            self: An instance of the CloudDeployer class.

        Returns:
            None

        Raises:
            None

        """
        # Load environment variables from .env file or system
        load_dotenv()
        self.set_environment_variables()

    def create_dockerfile(self):
        """
        Creates a Dockerfile for the application.

        Parameters:
            self: An instance of the CloudDeployer class.

        Returns:
            None

        Raises:
            None

        This method creates a Dockerfile in the current directory with the specified content.
        The Dockerfile is used to build a Docker image for the application.
        The content of the Dockerfile includes instructions to use the Python 3.11-slim base image,
        set the working directory to /app, copy the current directory contents into the container,
        install the required Python packages (flask, praisonai, gunicorn, and markdown),
        expose port 8080, and run the application using Gunicorn.
        """
        with open("Dockerfile", "w") as file:
            file.write("FROM python:3.11-slim\n")
            file.write("WORKDIR /app\n")
            file.write("COPY . .\n")
            file.write("RUN pip install flask praisonai==4.6.50 gunicorn markdown\n")
            file.write("EXPOSE 8080\n")
            file.write('CMD ["gunicorn", "-b", "0.0.0.0:8080", "api:app"]\n')
            
    def create_api_file(self):
        """
        Creates an API file for the application.

        Parameters:
            self (CloudDeployer): An instance of the CloudDeployer class.

        Returns:
            None

        This method creates an API file named "api.py" in the current directory. The file contains a basic Flask application that uses the PraisonAI library to run a simple agent and returns the output as an HTML page. The application listens on the root path ("/") and uses the Markdown library to format the output.
        """
        with open("api.py", "w") as file:
            file.write("from flask import Flask\n")
            file.write("from praisonai import PraisonAI\n")
            file.write("import markdown\n")
            file.write("import bleach\n\n")
            file.write("app = Flask(__name__)\n\n")
            file.write("def basic():\n")
            file.write("    praisonai = PraisonAI(agent_file=\"agents.yaml\")\n")
            file.write("    return praisonai.run()\n\n")
            file.write("@app.route('/')\n")
            file.write("def home():\n")
            file.write("    output = basic()\n")
            file.write("    rendered = markdown.markdown(str(output))\n")
            file.write("    safe_html = bleach.clean(rendered, tags=bleach.sanitizer.ALLOWED_TAGS, attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES)\n")
            file.write("    return f'<html><body>{safe_html}</body></html>'\n\n")
            file.write("if __name__ == \"__main__\":\n")
            file.write("    import os\n")
            file.write("    app.run(debug=os.environ.get('DEBUG', 'false').lower() == 'true')\n")
    
    def set_environment_variables(self):
        """Sets environment variables with fallback to .env values or defaults."""
        from praisonai.llm.env import resolve_llm_endpoint
        ep = resolve_llm_endpoint()
        
        os.environ["OPENAI_MODEL_NAME"] = ep.model
        os.environ["OPENAI_API_KEY"] = ep.api_key or "Enter your API key"
        os.environ["OPENAI_API_BASE"] = ep.base_url

    def run_commands(self):
        """
        Sets environment variables with fallback to .env values or defaults.

        Parameters:
            None

        Returns:
            None

        Raises:
            None

        This method sets environment variables for the application. It uses the `os.environ` dictionary to set the following environment variables:

        - `OPENAI_MODEL_NAME`: The name of the OpenAI model to use. If not specified in the .env file, it defaults to "gpt-4o-mini".
        - `OPENAI_API_KEY`: The API key for accessing the OpenAI API. If not specified in the .env file, it defaults to "Enter your API key".
        - `OPENAI_API_BASE`: The base URL for the OpenAI API. If not specified in the .env file, it defaults to "https://api.openai.com/v1".
        """
        self.create_api_file()
        self.create_dockerfile()
        """Runs a sequence of shell commands for deployment, continues on error."""
        
        # Get project ID upfront for Windows compatibility
        try:
            result = subprocess.run(['gcloud', 'config', 'get-value', 'project'], 
                                  capture_output=True, text=True, check=True)
            project_id = result.stdout.strip()
        except subprocess.CalledProcessError:
            print("ERROR: Failed to get GCP project ID. Ensure gcloud is configured.")
            return
        
        # Get environment variables
        from praisonai.llm.env import resolve_llm_endpoint
        ep = resolve_llm_endpoint()
        openai_model = ep.model
        openai_key = ep.api_key or 'Enter your API key'
        openai_base = ep.base_url
        
        # Create temporary env vars file to avoid exposing secrets in argv
        import tempfile
        import yaml
        import os
        
        env_vars_file = None
        try:
            # Create secure temp file for environment variables
            fd, env_vars_file = tempfile.mkstemp(suffix=".yaml", prefix="praisonai-deploy-")
            os.close(fd)
            os.chmod(env_vars_file, 0o600)  # Secure file permissions
            
            # Write env vars to file instead of passing in argv
            env_vars = {
                "OPENAI_MODEL_NAME": openai_model,
                "OPENAI_API_KEY": openai_key,
                "OPENAI_API_BASE": openai_base
            }
            
            with open(env_vars_file, "w") as f:
                yaml.safe_dump(env_vars, f)
            
            # Build commands with secure env vars file
            commands = [
                ['gcloud', 'auth', 'configure-docker', 'us-central1-docker.pkg.dev'],
                ['gcloud', 'artifacts', 'repositories', 'create', 'praisonai-repository', 
                 '--repository-format=docker', '--location=us-central1'],
                ['docker', 'build', '--platform', 'linux/amd64', '-t', 
                 f'gcr.io/{project_id}/praisonai-app:latest', '.'],
                ['docker', 'tag', f'gcr.io/{project_id}/praisonai-app:latest',
                 f'us-central1-docker.pkg.dev/{project_id}/praisonai-repository/praisonai-app:latest'],
                ['docker', 'push', 
                 f'us-central1-docker.pkg.dev/{project_id}/praisonai-repository/praisonai-app:latest'],
                ['gcloud', 'run', 'deploy', 'praisonai-service', 
                 '--image', f'us-central1-docker.pkg.dev/{project_id}/praisonai-repository/praisonai-app:latest',
                 '--platform', 'managed', '--region', 'us-central1', '--allow-unauthenticated',
                 '--env-vars-file', env_vars_file]
            ]
            
            # Run commands with appropriate handling for each platform
            for i, cmd in enumerate(commands):
                try:
                    if i == 0:  # First command (gcloud auth configure-docker)
                        if platform.system() != 'Windows':
                            # On Unix, pipe 'yes' to auto-confirm
                            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                            proc.communicate(input=b'Y\n')
                            if proc.returncode != 0:
                                raise subprocess.CalledProcessError(proc.returncode, cmd)
                        else:
                            # On Windows, try with --quiet flag to avoid prompts
                            cmd_with_quiet = cmd + ['--quiet']
                            try:
                                subprocess.run(cmd_with_quiet, check=True)
                            except subprocess.CalledProcessError:
                                # If --quiet fails, try without it
                                print("Note: You may need to manually confirm the authentication prompt")
                                subprocess.run(cmd, check=True)
                    else:
                        # Run other commands normally
                        subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"ERROR: Command failed with exit status {e.returncode}")
                    # Commands 2 (build) and 4 (push) and 5 (deploy) are critical
                    if i in [2, 4, 5]:
                        print("Critical command failed. Aborting deployment.")
                        return
                    print(f"Continuing with the next command...")
        
        finally:
            # Always cleanup the temporary env vars file
            if env_vars_file:
                try:
                    os.remove(env_vars_file)
                except Exception:
                    pass  # Don't fail deployment if cleanup fails

# Usage
if __name__ == "__main__":
    deployer = CloudDeployer()
    deployer.run_commands()
