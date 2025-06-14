# Claude Code Integration with PraisonAI Agents

This document describes the integration of Claude Code with PraisonAI Agents, allowing AI agents to intelligently decide when to use Claude Code for file modifications and coding tasks.

## Overview

The refactored implementation replaces direct `litellm` usage with `praisonaiagents`, making Claude Code a custom tool that the AI agent can choose to use based on the user's request. This provides better intelligence and flexibility while maintaining backward compatibility.

## Key Features

### 🤖 Agent-Driven Decision Making
- AI agent intelligently decides when to use Claude Code vs. regular responses
- No manual detection logic - the agent understands context
- Automatic tool selection based on request type

### 🔧 Claude Code as a Custom Tool
- Claude Code is implemented as a tool function for PraisonAI Agents
- Executes `claude --dangerously-skip-permissions -p "query"`
- Supports `--continue` flag for conversation continuity
- Git operations with automatic branch creation and PR URLs

### ⚙️ Flexible Configuration
- CLI flag: `praisonai code --claudecode`
- UI toggle: "Enable Claude Code (file modifications & coding)"
- Environment variable: `PRAISONAI_CLAUDECODE_ENABLED=true`

### 🔄 Backward Compatibility
- Falls back to `litellm` if `praisonaiagents` is not available
- Maintains all existing functionality
- No breaking changes to existing workflows

## Architecture

### Agent Instructions

The agent receives these instructions to guide tool usage:

```
You are a helpful AI assistant. Use the available tools when needed to provide comprehensive responses.

If Claude Code tool is available and the user's request involves:
- File modifications, code changes, or implementation tasks
- Creating, editing, or debugging code
- Project setup or development tasks
- Git operations or version control

Then use the Claude Code tool to handle those requests.

For informational questions, explanations, or general conversations, respond normally without using Claude Code.
```

### Tool Function: `claude_code_tool`

```python
async def claude_code_tool(query: str) -> str:
    """
    Execute Claude Code CLI commands for file modifications and coding tasks.
    
    Args:
        query: The user's request that requires file modifications or coding assistance
        
    Returns:
        The output from Claude Code execution
    """
```

**Features:**
- Executes Claude Code with `--dangerously-skip-permissions`
- Supports conversation continuity with `--continue` flag
- Automatic git branch creation and management
- PR URL generation for GitHub repositories
- 5-minute timeout for long operations
- Comprehensive error handling

### Available Tools

When Claude Code is enabled, the agent has access to:

1. **Claude Code Tool** - For file modifications and coding tasks
2. **Tavily Web Search** - For internet research (if API key configured)

The agent decides which tool(s) to use based on the user's request.

## Usage

### Command Line Interface

```bash
# Enable Claude Code integration
praisonai code --claudecode

# Use regular mode (no Claude Code)
praisonai code
```

### Environment Variables

```bash
# Force enable Claude Code (overrides UI setting)
export PRAISONAI_CLAUDECODE_ENABLED=true

# Set repository path (defaults to current directory)
export PRAISONAI_CODE_REPO_PATH=/path/to/your/repo
```

### UI Settings

In the PraisonAI Code UI, you can:
- Toggle "Enable Claude Code (file modifications & coding)" switch
- Setting is saved to database for persistence
- CLI flag takes precedence over UI setting

## Examples

### File Modification Request
**User:** "Create a new Python function to calculate fibonacci numbers"

**Agent Decision:** Uses Claude Code tool → Creates/modifies files → Returns implementation details

### Informational Request  
**User:** "How does fibonacci algorithm work?"

**Agent Decision:** Responds normally → Provides explanation without file modifications

### Mixed Request
**User:** "Explain how sorting works and implement quicksort in Python"

**Agent Decision:** May use Claude Code tool for implementation → Provides both explanation and code files

## Git Integration

When Claude Code makes changes and git is available:

1. **Automatic Branch Creation:** Creates `claude-code-YYYYMMDD_HHMMSS` branch
2. **Commit Changes:** Commits all modifications with descriptive message
3. **Remote Push:** Pushes branch to remote repository (if configured)
4. **PR URL Generation:** Generates GitHub PR creation URL

Example output:
```
📋 **Pull Request Created:**
https://github.com/user/repo/compare/main...claude-code-20241210_143022?quick_pull=1
```

## Error Handling

### Graceful Degradation
- If `praisonaiagents` unavailable → Falls back to `litellm`
- If Claude Code CLI unavailable → Agent works without the tool
- If git unavailable → Code changes without git operations
- Network issues → Continues with local operations

### Error Messages
- Clear error reporting in streaming responses
- Timeout handling for long operations
- Detailed logging for debugging

## Implementation Details

### File Structure
```
src/praisonai/praisonai/
├── cli.py                 # Added --claudecode flag
└── ui/
    └── code.py           # Refactored to use praisonaiagents
```

### Key Functions

1. **`handle_with_praisonai_agents()`** - Main agent execution handler
2. **`handle_with_litellm()`** - Fallback for backward compatibility  
3. **`claude_code_tool()`** - Claude Code tool implementation
4. **Settings management** - UI toggles and persistence

### Dependencies

**Required:**
- `praisonaiagents` - Core agent framework
- `subprocess` - For Claude Code CLI execution
- `chainlit` - UI framework

**Optional:**
- `tavily` - Web search capability
- `git` - Version control operations
- `claude` CLI - File modification capabilities

## Testing

Use the included test script to verify the integration:

```bash
python test_claude_code_integration.py
```

Tests verify:
- Import functionality
- PraisonAI Agents availability
- Claude Code CLI availability
- Environment variable configuration
- Basic tool execution

## Migration Guide

### From Previous Implementation

The previous implementation used direct Claude Code detection logic. The new implementation:

1. **Replaces detection logic** with agent intelligence
2. **Maintains same UI/CLI interfaces** for easy migration
3. **Preserves all existing functionality** while adding flexibility
4. **Requires no user workflow changes**

### Upgrading

1. Ensure `praisonaiagents` is installed
2. Update PraisonAI to include the refactored code
3. Use `--claudecode` flag or UI toggle as before
4. Existing settings and workflows continue working

## Best Practices

### When to Enable Claude Code
- File modification projects
- Code development workflows  
- Repository maintenance tasks
- Implementation and debugging sessions

### When to Disable Claude Code
- Read-only analysis
- Documentation-only sessions
- Learning and educational content
- General Q&A conversations

### Configuration Recommendations
- Use CLI flag for development sessions
- Use UI toggle for mixed workflows
- Set environment variables for CI/CD integration
- Configure repository path for multi-project setups

## Troubleshooting

### Common Issues

**Agent doesn't use Claude Code tool:**
- Verify Claude Code is enabled (`--claudecode` flag or UI toggle)
- Check that request involves file modifications
- Ensure `praisonaiagents` is installed

**Claude Code tool fails:**
- Verify `claude` CLI is installed and in PATH
- Check repository permissions
- Confirm git repository status (if git operations needed)

**Fallback to litellm:**
- Install `praisonaiagents`: `pip install praisonaiagents`
- Check import errors in logs
- Verify Python environment compatibility

### Debug Information

Enable verbose logging:
```bash
export LOGLEVEL=DEBUG
praisonai code --claudecode
```

Check environment:
```python
import os
print("Claude Code enabled:", os.getenv("PRAISONAI_CLAUDECODE_ENABLED"))
print("Repo path:", os.getenv("PRAISONAI_CODE_REPO_PATH"))
```

## Future Enhancements

### Planned Features
- Real-time streaming from PraisonAI Agents
- Enhanced git workflow integration
- Multi-repository support
- Advanced tool coordination
- Performance optimizations

### Extension Points
- Additional coding tools integration
- Custom agent instructions
- Workflow templates
- Integration with other development tools

---

For technical support or questions, please refer to the main PraisonAI documentation or submit issues to the repository.