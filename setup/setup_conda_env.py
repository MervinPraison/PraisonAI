import subprocess
import os
import sys
import platform

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, 'setup_conda_env.sh')
    
    if platform.system() == 'Windows':
        print("Windows detected. Please run the setup_conda_env.sh script manually in Git Bash or WSL.")
        print(f"Script location: {script_path}")
        sys.exit(1)
    
    try:
        subprocess.check_call(['bash', script_path])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running the setup script: {e}")
        print("Setup failed. Please check the error message above and try to resolve the issue.")
        sys.exit(1)
    
    print("Conda environment setup completed successfully!")

if __name__ == "__main__":
    main()