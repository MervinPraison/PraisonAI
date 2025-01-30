#!/usr/bin/env python3
"""Test runner for all tools."""

import os
import glob
import logging
import subprocess

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run all tool files."""
    logger.info("Starting tests...")
    
    # Get all *_tools.py files
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    tool_files = glob.glob(os.path.join(tools_dir, "*_tools.py"))
    
    # Run each tool file
    for tool_file in sorted(tool_files):
        module_name = os.path.basename(tool_file)
        logger.info(f"\nRunning {module_name}...")
        
        try:
            # Run the tool file directly
            result = subprocess.run(
                ["python3", tool_file],
                capture_output=True,
                text=True,
                cwd=tools_dir
            )
            
            # Log output
            if result.stdout:
                logger.info(f"Output:\n{result.stdout}")
            if result.stderr:
                logger.error(f"Errors:\n{result.stderr}")
            
            if result.returncode == 0:
                logger.info(f" {module_name} completed successfully")
            else:
                logger.error(f" {module_name} failed with return code {result.returncode}")
        
        except Exception as e:
            logger.error(f"Error running {module_name}: {str(e)}")
            continue
    
    logger.info("\nAll tests completed!")

if __name__ == "__main__":
    main()
