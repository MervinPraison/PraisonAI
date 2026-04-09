# PraisonAI PR Reviewer Setup Guide

This guide helps you set up automated PR reviews using PraisonAI agents.

## Prerequisites

1. **GitHub App**: Create a GitHub App with the following permissions:
   - Repository permissions: Contents (read), Pull requests (write), Issues (write)
   - Subscribe to Pull request and Issue comment events

2. **Repository Secrets**: Add the following secrets to your repository:
   - `APP_ID`: Your GitHub App ID
   - `PRIVATE_KEY`: Your GitHub App private key (PEM format)
   - `OPENAI_API_KEY`: Your OpenAI API key for the LLM

## Setup Steps

1. **Copy the workflow file**: Copy `examples/yaml/praisonai-pr-review.yml.template` to `.github/workflows/praisonai-pr-review.yml` in your default branch.

2. **Configure the reviewer agent**: The default `.github/praisonai-reviewer.yaml` configuration is included, but you can customize it to modify the review behavior.

3. **Test the integration**:
   - Create a test PR to trigger automatic review
   - Or comment `@praisonai` on an existing PR to trigger manual review

## Trigger Mechanisms

- **Automatic**: Runs on PR open, sync, reopen, and ready_for_review events
- **Manual**: Comment `@praisonai` on any PR (restricted to repository owners, members, and collaborators)

## Security Notes

- Comment triggers are restricted to repository owners, members, and collaborators
- The workflow uses GitHub App authentication with minimal required permissions
- All secrets are properly handled through GitHub's secret management