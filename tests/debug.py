# tests/debug.py
import tracemalloc
import logging
import warnings
import sys
import traceback

# Enable Tracemalloc
tracemalloc.start()

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(lineno)d - %(message)s')

# Function to Log Warnings with Traceback
def warn_with_traceback(message, category, filename, lineno, file=None, line=None):
    log = file if hasattr(file, 'write') else sys.stderr
    traceback.print_stack(file=log)
    log.write(warnings.formatwarning(message, category, filename, lineno, line))

# Override showwarning
warnings.showwarning = warn_with_traceback