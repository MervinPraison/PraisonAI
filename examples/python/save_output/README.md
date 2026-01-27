# Save Agent Output Examples

Examples demonstrating different methods to save agent output to files.

## Examples

| File | Method | Description |
|------|--------|-------------|
| `01_write_file_tool.py` | write_file Tool | Agent decides when/what to save |
| `02_task_output_file.py` | Task.output_file | Auto-save task result |
| `03_workflow_output_file.py` | Workflow output_file | Save workflow step output |
| `04_manual_save.py` | Manual | Full control over saving |

## Setup

```bash
pip install praisonaiagents
export OPENAI_API_KEY="your-key"
```

## Run Examples

```bash
python 01_write_file_tool.py
python 02_task_output_file.py
python 03_workflow_output_file.py
python 04_manual_save.py
```

## Which Method to Use?

- **write_file Tool**: When agent needs to decide what to save
- **Task.output_file**: For task-based workflows with auto-save
- **Workflow output_file**: For YAML workflows with variable substitution
- **Manual**: When you need full control over the saving process
