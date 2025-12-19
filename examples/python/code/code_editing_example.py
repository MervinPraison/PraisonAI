"""
Code Editing Tools Example

Demonstrates how to use PraisonAI's code editing tools with SEARCH/REPLACE diffs.
"""

from praisonai.code import (
    set_workspace,
    code_read_file,
    code_write_file,
    code_apply_diff,
    code_list_files,
    code_execute_command,
    CODE_TOOLS
)

# Set workspace
set_workspace(".")

# List files
print("Files in current directory:")
files = code_list_files(".", recursive=False)
for f in files:
    print(f"  {f}")

# Read a file
print("\nReading example file:")
try:
    content = code_read_file("README.md", start_line=1, end_line=10)
    print(content)
except Exception as e:
    print(f"  File not found: {e}")

# Write a file
print("\nWriting test file:")
code_write_file("test_output.txt", "Hello from PraisonAI Code Tools!")
print("  Created test_output.txt")

# Apply a diff
print("\nApplying diff:")
diff = """
<<<<<<< SEARCH
Hello from PraisonAI Code Tools!
=======
Hello from PraisonAI Code Tools!
This line was added by a diff.
>>>>>>> REPLACE
"""
result = code_apply_diff("test_output.txt", diff)
print(f"  {result}")

# Execute command
print("\nExecuting command:")
output = code_execute_command("cat test_output.txt")
print(f"  {output}")

# Cleanup
import os
os.remove("test_output.txt")
print("\nCleanup complete.")
