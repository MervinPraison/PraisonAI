import subprocess
import sys
import os

def build(setup_kwargs):
    try:
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Construct the path to post_install.py
        post_install_script = os.path.join(script_dir, 'post_install.py')
        
        # Run the post_install.py script
        subprocess.check_call([sys.executable, post_install_script])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running the post-install script: {e}")
        sys.exit(1)
    return setup_kwargs

if __name__ == "__main__":
    build({})