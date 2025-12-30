#!/bin/bash
# MCP CLI Tools Examples
#
# Demonstrates the new CLI commands for MCP tool management:
# - praisonai mcp tools search
# - praisonai mcp tools info
# - praisonai mcp tools schema
# - praisonai mcp list-tools (with pagination)
#
# Usage:
#   chmod +x cli_tools_example.sh
#   ./cli_tools_example.sh

echo "========================================"
echo "MCP CLI Tools Examples"
echo "MCP Protocol Version: 2025-11-25"
echo "========================================"

echo ""
echo "--- List Tools (with pagination) ---"
echo "Command: praisonai mcp list-tools --limit 5"
praisonai mcp list-tools --limit 5

echo ""
echo "--- List Tools (JSON output) ---"
echo "Command: praisonai mcp list-tools --json --limit 3"
praisonai mcp list-tools --json --limit 3

echo ""
echo "--- Tools Help ---"
echo "Command: praisonai mcp tools --help"
praisonai mcp tools --help

echo ""
echo "--- Search Tools ---"
echo "Command: praisonai mcp tools search 'workflow'"
praisonai mcp tools search "workflow"

echo ""
echo "--- Search Read-Only Tools ---"
echo "Command: praisonai mcp tools search --read-only"
praisonai mcp tools search --read-only

echo ""
echo "--- Search with JSON Output ---"
echo "Command: praisonai mcp tools search 'memory' --json"
praisonai mcp tools search "memory" --json

echo ""
echo "========================================"
echo "Examples completed!"
echo "========================================"
