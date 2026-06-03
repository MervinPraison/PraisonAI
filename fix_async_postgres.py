#!/usr/bin/env python3

import re

# Read the file
with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai/praisonai/persistence/conversation/async_postgres.py', 'r') as f:
    content = f.read()

# Remove all sync wrapper methods (lines that contain "run_sync")
lines = content.split('\n')
output_lines = []
skip_lines = 0

for line in lines:
    if skip_lines > 0:
        skip_lines -= 1
        continue
    
    # If we find a sync wrapper method, skip it and the next 2-3 lines
    if 'run_sync(' in line and 'def ' in line:
        # Look ahead to find the end of this method
        skip_lines = 2  # Skip the method line and return line
        continue
    
    # Rename async methods by removing "async_" prefix
    if 'async def async_' in line:
        line = line.replace('async def async_', 'async def ')
        
    output_lines.append(line)

# Write the updated content
with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai/praisonai/persistence/conversation/async_postgres.py', 'w') as f:
    f.write('\n'.join(output_lines))

print("Updated async_postgres.py successfully")