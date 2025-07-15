#!/usr/bin/env python3
"""
Script to fix the deprecated .dict() usage in Jupyter notebook
"""
import json
import sys

def fix_notebook():
    notebook_path = "examples/cookbooks/Programming_Code_Analysis_Agents/ZeroScript_AI_TestExecutor.ipynb"
    
    try:
        # Read the notebook
        with open(notebook_path, 'r') as f:
            notebook = json.load(f)
        
        # Find and fix the cell with .dict() usage
        for cell in notebook.get('cells', []):
            if cell.get('cell_type') == 'code':
                source = cell.get('source', [])
                # Convert source to string if it's a list
                source_str = ''.join(source) if isinstance(source, list) else source
                
                # Check if this cell contains the problematic .dict() usage or hasattr check
                if 'result_obj.dict()' in source_str or 'hasattr(result_obj, "dict")' in source_str:
                    print(f"Found cell with .dict() usage, fixing...")
                    # Replace .dict() with .model_dump() and fix hasattr check for backward compatibility
                    fixed_source = source_str.replace('result_obj.dict()', 'result_obj.model_dump()').replace('hasattr(result_obj, "dict")', 'hasattr(result_obj, "model_dump")')
                    
                    # Convert back to list format if needed
                    if isinstance(source, list):
                        cell['source'] = fixed_source.splitlines(True)
                    else:
                        cell['source'] = fixed_source
                    
                    print("Fixed .dict() usage")
                    break
        
        # Write the fixed notebook back
        with open(notebook_path, 'w') as f:
            json.dump(notebook, f, indent=2)
        
        print(f"Successfully updated {notebook_path}")
        return True
        
    except Exception as e:
        print(f"Error fixing notebook: {e}")
        return False

if __name__ == "__main__":
    success = fix_notebook()
    sys.exit(0 if success else 1)