# Claude Code Integration in PraisonAI UI

This document describes the Claude Code integration implemented in PraisonAI UI.

## Overview

The PraisonAI UI now includes intelligent integration with Claude Code, allowing users to perform file modifications and git operations directly through the chat interface while maintaining the existing conversational capabilities.

## Features

### 🧠 **Smart Detection**
The system automatically detects when user messages require file modifications or git operations based on keywords and context:
- **Modification keywords**: create, modify, update, edit, change, fix, implement, add, remove, delete, refactor, write, generate, build, install, setup, configure, deploy
- **Git keywords**: commit, branch, git, pull request, pr, merge, push
- **File keywords**: file, files, code, script, function, class, module, package, library, component, feature

### ⚙️ **Dual Mode Operation**
- **Claude Code Mode**: For file modifications, implementations, and git operations
- **LLM Mode**: For questions, explanations, and informational queries

### 🔧 **File Modifications**
- Executes `claude --dangerously-skip-permissions -p "query"`
- Real-time streaming of Claude Code output
- Automatic context gathering from repository

### 🌲 **Git Operations**
- Automatic branch creation with timestamp (`claude-code-YYYYMMDD-HHMMSS`)
- Fallback to regular execution if no git repository
- Smart branch detection (won't create new branch if already on non-main branch)

### 🔗 **Pull Request Generation**
- Automatic PR URL generation after successful changes
- Pre-filled PR title and description
- Lists modified files
- Includes original request context

### 🔄 **Conversation Continuity**
- Uses `--continue` flag for related requests
- Maintains conversation context across modifications
- Session-based continuation tracking

## Configuration

### Environment Variables

```bash
# Enable/disable Claude Code (default: true)
CLAUDE_CODE_ENABLED=true

# Repository path for operations (default: current directory)
PRAISONAI_CODE_REPO_PATH=/path/to/your/repo

# Claude executable path (auto-detected)
# Ensure 'claude' is in your PATH or set explicitly
```

### UI Settings

The chat interface includes a toggle switch:
- **"Enable Claude Code (file modifications & git operations)"**
- Can be toggled on/off per session
- Setting is persisted across sessions

## Usage Examples

### File Modifications
```
User: "Create a new Python function to calculate fibonacci numbers"
→ Uses Claude Code mode, creates/modifies files, shows PR link

User: "Fix the bug in the authentication module"
→ Uses Claude Code mode, modifies files, creates branch and PR

User: "Add error handling to the database connection"
→ Uses Claude Code mode, implements changes
```

### Informational Queries
```
User: "How does the authentication system work?"
→ Uses LLM mode, provides explanation with repository context

User: "What are the dependencies of this project?"
→ Uses LLM mode, analyzes and explains dependencies
```

### Git Operations
```
User: "Commit these changes and create a pull request"
→ Uses Claude Code mode, handles git operations

User: "Create a new branch for this feature"
→ Uses Claude Code mode, handles branch creation
```

## Technical Implementation

### Detection Logic
```python
def should_use_claude_code(message_content: str) -> bool:
    # Checks user session setting and environment variables
    # Analyzes message for modification/git keywords
    # Returns True for file operations, False for informational queries
```

### Execution Flow
1. **Message Analysis**: Determine if Claude Code or LLM mode
2. **Branch Setup**: Create git branch if repository exists
3. **Claude Code Execution**: Run with `--dangerously-skip-permissions`
4. **Output Streaming**: Real-time display of results
5. **PR Generation**: Create GitHub PR URL if changes made

### Error Handling
- Graceful fallback if Claude Code not available
- Continues without git if no repository
- Detailed error logging and user feedback

## Prerequisites

1. **Claude Code CLI**: Must be installed and available in PATH
2. **Git Repository**: Optional, but required for git operations
3. **GitHub Repository**: Optional, but required for PR generation

## Installation

The feature is automatically available in the PraisonAI UI. Ensure:

1. Claude Code CLI is installed: [https://claude.ai/code](https://claude.ai/code)
2. Repository context is properly configured
3. Environment variables are set as needed

## Limitations

- Requires Claude Code CLI to be installed and accessible
- Git operations require a valid git repository
- PR generation works only with GitHub repositories
- Some complex modifications may require manual intervention

## Security Considerations

- Uses `--dangerously-skip-permissions` flag for file modifications
- Operates within the configured repository path
- All operations are logged for audit purposes
- Users should review changes before merging PRs

## Backward Compatibility

- Existing chat functionality remains unchanged
- Non-modification queries use standard LLM responses
- Can be disabled via environment variable or UI toggle
- Falls back gracefully if Claude Code is unavailable