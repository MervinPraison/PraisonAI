import subprocess
import sys
import os

def main():
    try:
        # Get the absolute path of the current file 
        current_file = os.path.abspath(__file__)
        
        # Get the directory of the current file
        script_dir = os.path.dirname(current_file) 
        
        # Construct the path to setup_conda_env.py
        setup_script = os.path.join(script_dir, 'setup_conda_env.py')
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running the setup script: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()