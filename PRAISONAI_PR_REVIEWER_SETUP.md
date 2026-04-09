# PraisonAI PR Reviewer Integration Guide

This guide provides step-by-step instructions for integrating PraisonAI as an automated PR reviewer in your GitHub CI/CD pipeline.

## Overview

PraisonAI PR Reviewer implements a **Zero-Code, Multi-Agent PR Review System** that deploys specialized agents to analyze pull requests from multiple perspectives:

- 🔐 **Security Reviewer**: Identifies vulnerabilities and security issues
- ⚡ **Performance Reviewer**: Analyzes for bottlenecks and inefficiencies  
- 📋 **Maintainability Reviewer**: Evaluates code quality and best practices
- 👨‍💼 **Lead Reviewer**: Synthesizes feedback and posts comprehensive reviews

## Architecture

This integration follows PraisonAI's **Agent-Centric** and **Protocol-Driven Core** design principles:

```
GitHub PR → @praisonai trigger → Multi-Agent Workflow → Comprehensive Review
```

The solution leverages:
- **GitHub Actions** for CI/CD orchestration
- **PraisonAI CLI** for agent execution
- **YAML Configuration** for agent team definition
- **GitHub CLI** for PR interaction

## Prerequisites

1. **Repository Setup**:
   - GitHub repository with Actions enabled
   - Required secrets configured (see [Secrets Configuration](#secrets-configuration))

2. **PraisonAI Installation**:
   - The workflow automatically installs PraisonAI via `pip install praisonai`
   - No additional dependencies required

3. **GitHub App/Token**:
   - GitHub App with required permissions OR
   - Personal Access Token with `repo` and `pull_requests` permissions

## Installation Steps

### Step 1: Copy Agent Configuration

The agent configuration is already provided at:
```
.github/praisonai-reviewer.yaml
```

This file defines the multi-agent team and their specific responsibilities.

### Step 2: Create GitHub Workflow

**IMPORTANT**: Due to GitHub App permissions, the workflow file must be manually created.

1. Copy the template from:
   ```
   examples/yaml/praisonai-pr-review.yml.template
   ```

2. Save it as:
   ```
   .github/workflows/praisonai-pr-review.yml
   ```

### Step 3: Configure Secrets

Add the following secrets to your repository (`Settings > Secrets and variables > Actions`):

| Secret | Description | Required |
|--------|-------------|----------|
| `APP_ID` | GitHub App ID | Yes (if using GitHub App) |
| `PRIVATE_KEY` | GitHub App private key | Yes (if using GitHub App) |
| `OPENAI_API_KEY` | OpenAI API key for LLM access | Yes |

**Alternative**: Use `GH_TOKEN` instead of GitHub App if you prefer PAT authentication.

### Step 4: Update Review Chain (Optional)

The review chain documentation has been updated to include PraisonAI:
```
CodeRabbit/Qodo → Gemini/PraisonAI (parallel) → Copilot → Claude (final)
```

This ensures PraisonAI integrates seamlessly with existing review workflows.

## Usage

### Manual Trigger

1. **Workflow Dispatch**: 
   - Go to `Actions > PraisonAI PR Review > Run workflow`
   - Enter the PR number to review

### Automatic Trigger

1. **Comment Trigger**:
   - Comment `@praisonai` on any pull request
   - Only repository owners, members, and collaborators can trigger

2. **With Instructions**:
   - `@praisonai focus on security vulnerabilities`
   - `@praisonai check performance and memory usage`
   - `@praisonai review for maintainability issues`

## Expected Output

When triggered, PraisonAI will post a comprehensive review with this structure:

```markdown
## 📋 Review Summary
[Brief overview and assessment]

## 🔍 General Feedback  
[Overall patterns and observations]

## 🎯 Specific Feedback
### 🔴 Critical
[Security vulnerabilities, breaking changes, major bugs]

### 🟡 High 
[Performance issues, design flaws, significant bugs]

### 🟢 Medium
[Code quality improvements, minor optimizations]

### 🔵 Low
[Documentation, naming suggestions, minor refactoring]

## ✅ Highlights
[Positive aspects worth mentioning]

---
*Review completed by PraisonAI Multi-Agent Team*
```

## Integration with Existing Workflows

PraisonAI integrates seamlessly with the existing review chain:

1. **Parallel Execution**: Runs alongside Gemini for faster reviews
2. **No Conflicts**: Uses unique trigger (`@praisonai`) to avoid interference
3. **Complementary Analysis**: Provides different perspectives from other tools
4. **Chain Continuation**: Claude final review incorporates PraisonAI feedback

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify `APP_ID` and `PRIVATE_KEY` secrets are correctly set
   - Ensure GitHub App has required permissions

2. **PraisonAI Installation Fails**:
   - Check if Python setup step completed successfully
   - Verify internet connectivity for pip installation

3. **Agent Execution Fails**:
   - Check `OPENAI_API_KEY` secret is valid
   - Verify agent configuration YAML syntax

4. **Permission Denied**:
   - Ensure triggering user has required repository permissions
   - Check workflow file permissions configuration

### Debug Steps

1. **Check Workflow Logs**:
   - Go to `Actions > PraisonAI PR Review`
   - Click on failed run to see detailed logs

2. **Validate Configuration**:
   - Ensure `.github/praisonai-reviewer.yaml` syntax is valid
   - Test agent configuration locally if possible

3. **Test Manual Trigger**:
   - Use workflow dispatch to isolate comment trigger issues

## Advanced Configuration

### Custom Agent Teams

Modify `.github/praisonai-reviewer.yaml` to:
- Add specialized agents (e.g., Architecture Reviewer)
- Adjust agent responsibilities
- Customize review output format

### Integration with External Tools

Extend agents to integrate with:
- Code quality tools (SonarQube, CodeClimate)
- Security scanners (Snyk, SAST tools)  
- Performance profilers

### Environment-Specific Reviews

Configure different agent teams for:
- Backend vs Frontend changes
- Different programming languages
- Specific project domains

## Performance Considerations

- **Execution Time**: Typically 3-5 minutes for comprehensive review
- **Rate Limits**: Respects GitHub API and OpenAI rate limits
- **Cost**: Uses OpenAI API - monitor usage for cost control
- **Parallel Execution**: Agents run concurrently for efficiency

## Security

- **Secret Handling**: All credentials stored securely in GitHub Secrets
- **Permissions**: Minimal required permissions for workflow execution
- **Code Access**: Review-only access, no code modification capabilities
- **Audit Trail**: All reviews logged in GitHub Actions logs

## Contributing

To improve the PraisonAI PR Reviewer:

1. **Agent Enhancement**: Improve agent prompts and capabilities
2. **Workflow Optimization**: Enhance GitHub Actions workflow
3. **Documentation**: Update guides and troubleshooting info
4. **Integration**: Add support for additional tools and platforms

## Support

For issues and questions:
1. Check this guide first
2. Review GitHub Actions logs
3. Open issue in PraisonAI repository
4. Tag with `ci/cd` and `pr-review` labels

---

*Generated as part of PraisonAI CI/CD PR Reviewer Integration (Issue #1329)*