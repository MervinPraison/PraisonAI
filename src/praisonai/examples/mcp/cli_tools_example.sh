#!/bin/bash
# MCP CLI Tools Examples
#
# Demonstrates the CLI commands for MCP tool management:
# - praisonai mcp list-tools (list all tools)
# - praisonai mcp tools search (search tools)
# - praisonai mcp tools info (show tool details)
# - praisonai mcp tools schema (show tool schema)
#
# Usage:
#   chmod +x cli_tools_example.sh
#   ./cli_tools_example.sh

echo "========================================"
echo "MCP CLI Tools Examples"
echo "MCP Protocol Version: 2025-11-25"
echo "========================================"

echo ""
echo "--- List All Tools ---"
echo "Command: praisonai mcp list-tools"
praisonai mcp list-tools

echo ""
echo "--- List Tools (JSON output) ---"
echo "Command: praisonai mcp list-tools --json"
praisonai mcp list-tools --json

echo ""
echo "--- Search Tools ---"
echo "Command: praisonai mcp tools search 'memory'"
praisonai mcp tools search "memory"

echo ""
echo "--- List Tools via tools command ---"
echo "Command: praisonai mcp tools list"
praisonai mcp tools list

echo ""
echo "--- Tools Help ---"
echo "Command: praisonai mcp tools help"
praisonai mcp tools help

echo ""
echo "--- MCP Help ---"
echo "Command: praisonai mcp --help"
praisonai mcp --help

echo ""
echo "========================================"
echo "Examples completed!"
echo "========================================"
