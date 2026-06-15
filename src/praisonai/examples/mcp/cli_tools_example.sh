#!/bin/bash
# MCP CLI Tools Examples
#
# Demonstrates the CLI commands for MCP tool management:
# - praisonai mcp list (list servers)
# - praisonai mcp sync (sync tool schemas)
# - praisonai mcp tools (list tools)
# - praisonai mcp describe (show tool schema)
#
# Usage:
#   chmod +x cli_tools_example.sh
#   ./cli_tools_example.sh

echo "========================================"
echo "MCP CLI Tools Examples"
echo "MCP Protocol Version: 2025-11-25"
echo "========================================"

echo ""
echo "--- List Configured Servers ---"
echo "Command: praisonai mcp list"
praisonai mcp list

echo ""
echo "--- List Servers (JSON output) ---"
echo "Command: praisonai mcp list --json"
praisonai mcp list --json

echo ""
echo "--- Sync Tool Schemas ---"
echo "Command: praisonai mcp sync"
praisonai mcp sync

echo ""
echo "--- List All Tools ---"
echo "Command: praisonai mcp tools"
praisonai mcp tools

echo ""
echo "--- List Tools (JSON output) ---"
echo "Command: praisonai mcp tools --json"
praisonai mcp tools --json

echo ""
echo "--- MCP Help ---"
echo "Command: praisonai mcp --help"
praisonai mcp --help

echo ""
echo "========================================"
echo "Examples completed!"
echo "========================================"
