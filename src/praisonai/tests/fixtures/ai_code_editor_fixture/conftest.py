# Create the conftest.py file with content
import sys
from pathlib import Path

# Add the src directory to Python path so mathlib can be imported
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
