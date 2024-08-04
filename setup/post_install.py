import subprocess
import sys
import os

def main():
    try:
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Construct the path to setup_conda_env.py
        setup_script = os.path.join(script_dir, 'setup_conda_env.py')
        
        # Run the setup_conda_env.py script
        subprocess.check_call([sys.executable, setup_script])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running the setup script: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()