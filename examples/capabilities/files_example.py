"""
Files Capabilities Example

Demonstrates file management using PraisonAI capabilities.
"""

from praisonai.capabilities import file_list

print("=== File List ===")
try:
    files = file_list()
    print(f"Files found: {len(files)}")
    for f in files[:5]:  # Show first 5
        print(f"  - {f.get('filename', 'unknown')}: {f.get('id', 'unknown')}")
except Exception as e:
    print(f"Note: {e}")
    print("File operations require files to be uploaded first.")

print("\n=== File Operations ===")
print("Available functions:")
print("  file_create(file_path, purpose='assistants')")
print("  file_list(purpose=None)")
print("  file_retrieve(file_id)")
print("  file_delete(file_id)")
print("  file_content(file_id)")

print("\nSee CLI: praisonai files list")
print("See CLI: praisonai files upload <file>")
