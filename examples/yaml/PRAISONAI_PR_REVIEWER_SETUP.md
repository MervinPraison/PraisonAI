# PraisonAI PR Reviewer Setup Guide

This guide explains how to set up PraisonAI as an automated pull request reviewer using GitHub Actions and GitHub Apps.

## Prerequisites
1. A GitHub App created within your organization or account.
2. The App must have the following permissions:
   - Pull Requests: Read & Write
   - Issues: Read & Write
   - Contents: Read
3. Generate a Private Key for the GitHub App.

## Setup Steps

1. Configure GitHub Secrets for your repository:
   - `PRAISONAI_APP_ID`: The App ID of your GitHub App.
   - `PRAISONAI_APP_PRIVATE_KEY`: The generated Private Key (PEM format).
   - `OPENAI_API_KEY` (or other LLM key) for PraisonAI to use.

2. Ensure `.github/workflows/praisonai-pr-review.yml` is present in your default branch.

3. Customize `.github/praisonai-reviewer.yaml` to configure the reviewing agents with specific roles.

## Triggering the Review
The review will run automatically upon PR creation and synchronization. You can also trigger it manually by commenting `@praisonai` on any pull request or issue.
