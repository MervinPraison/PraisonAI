import os
import sys
import subprocess
import logging

def install_playwright():
    """Install playwright browsers."""
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)
        logging.info("Playwright browsers installed successfully")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install playwright browsers: {e}")
    except Exception as e:
        logging.error(f"Unexpected error installing playwright browsers: {e}")

def main():
    """Post-installation script."""
    # Check if this is a chat or code installation
    if any(extra in sys.argv for extra in ['chat', 'code']):
        install_playwright()

if __name__ == "__main__":
    main()