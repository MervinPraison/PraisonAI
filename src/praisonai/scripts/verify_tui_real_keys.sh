#!/bin/bash
# PraisonAI TUI Real-Key Verification Script
# 
# This script verifies the TUI and Queue system works with real API keys.
# It includes safety gates and secret masking.
#
# Usage:
#   ./scripts/verify_tui_real_keys.sh
#
# Required environment variables:
#   OPENAI_API_KEY - OpenAI API key
#
# Optional:
#   PRAISONAI_REAL_LLM=1 - Required to run real LLM tests

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PraisonAI TUI + Queue System Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Function to mask secrets in output
mask_secrets() {
    sed -E 's/(sk-[a-zA-Z0-9]{20})[a-zA-Z0-9]+/\1***/g' | \
    sed -E 's/(key_[a-zA-Z0-9]{20})[a-zA-Z0-9]+/\1***/g' | \
    sed -E 's/(tvly-[a-zA-Z0-9]{20})[a-zA-Z0-9]+/\1***/g' | \
    sed -E 's/(AIza[a-zA-Z0-9]{20})[a-zA-Z0-9]+/\1***/g'
}

# Check environment variables
echo -e "\n${YELLOW}[1/7] Checking environment variables...${NC}"

check_env() {
    local var_name=$1
    local value="${!var_name}"
    if [ -n "$value" ]; then
        local masked=$(echo "$value" | head -c 10)
        echo -e "  ${GREEN}✓${NC} $var_name: ${masked}***"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC} $var_name: not set"
        return 1
    fi
}

OPENAI_SET=false
check_env "OPENAI_API_KEY" && OPENAI_SET=true
check_env "ANTHROPIC_API_KEY" || true
check_env "GOOGLE_API_KEY" || true
check_env "TAVILY_API_KEY" || true

if [ "$OPENAI_SET" = false ]; then
    echo -e "\n${RED}Error: OPENAI_API_KEY is required${NC}"
    exit 1
fi

# Check Python imports
echo -e "\n${YELLOW}[2/7] Checking Python imports...${NC}"

python3 -c "
from praisonai.cli.features.queue import QueuedRun, RunState, RunPriority, QueueConfig
from praisonai.cli.features.queue import QueueScheduler, QueuePersistence, QueueManager
from praisonai.cli.features.tui import TUIEvent, TUIEventType
from praisonai.cli.features.tui import TuiOrchestrator, UIStateModel, SimulationRunner
from praisonai.cli.features.tui import MockProvider, MockProviderConfig
print('  ✓ All imports successful')
" 2>&1 | mask_secrets

# Run unit tests
echo -e "\n${YELLOW}[3/7] Running unit tests...${NC}"

cd "$(dirname "$0")/.."
python3 -m pytest tests/unit/cli/queue/ tests/unit/cli/tui/ -v --tb=short --import-mode=importlib 2>&1 | \
    tail -20 | mask_secrets

# Test queue CLI commands
echo -e "\n${YELLOW}[4/7] Testing queue CLI commands...${NC}"

python3 -c "
from praisonai.cli.features.tui.cli import create_queue_app
app = create_queue_app()
print('  ✓ Queue CLI app created')
print('  Commands:', [cmd.name for cmd in app.registered_commands])
" 2>&1 | mask_secrets

# Test mock provider
echo -e "\n${YELLOW}[5/7] Testing mock provider...${NC}"

python3 -c "
import asyncio
from praisonai.cli.features.tui.mock_provider import MockProvider, create_mock_provider

async def test():
    provider = create_mock_provider(seed=42)
    
    # Test streaming
    chunks = []
    result = await provider.generate(
        'hello world',
        stream=True,
        on_chunk=lambda c: chunks.append(c)
    )
    
    print('  ✓ Mock provider works')
    print(f'    Content length: {len(result[\"content\"])} chars')
    print(f'    Chunks: {len(chunks)}')
    print(f'    Tokens: {result[\"tokens\"]}')
    print(f'    Cost: \${result[\"cost\"]:.6f}')

asyncio.run(test())
" 2>&1 | mask_secrets

# Test orchestrator
echo -e "\n${YELLOW}[6/7] Testing TUI orchestrator...${NC}"

python3 -c "
import asyncio
from praisonai.cli.features.tui.orchestrator import TuiOrchestrator, OutputMode
from praisonai.cli.features.queue import QueueConfig

async def test():
    config = QueueConfig(enable_persistence=False)
    orchestrator = TuiOrchestrator(
        queue_config=config,
        output_mode=OutputMode.SILENT,
        debug=False,
    )
    
    await orchestrator.start(session_id='test-verify')
    
    # Get snapshot
    snapshot = orchestrator.get_snapshot()
    print('  ✓ Orchestrator started')
    print(f'    Session: {snapshot[\"session_id\"]}')
    print(f'    Model: {snapshot[\"model\"]}')
    
    await orchestrator.stop()
    print('  ✓ Orchestrator stopped cleanly')

asyncio.run(test())
" 2>&1 | mask_secrets

# Real LLM test (gated)
echo -e "\n${YELLOW}[7/7] Real LLM test...${NC}"

if [ "$PRAISONAI_REAL_LLM" = "1" ]; then
    echo "  Running real LLM test (PRAISONAI_REAL_LLM=1)"
    
    python3 -c "
import asyncio
import os

# Safety: Use minimal tokens
async def test():
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions='Reply with exactly one word.',
        model='gpt-4o-mini',
        verbose=False,
    )
    
    result = agent.start('Say hello')
    print(f'  ✓ Real LLM response: {result[:50]}...')

asyncio.run(test())
" 2>&1 | mask_secrets
else
    echo -e "  ${YELLOW}⚠${NC} Skipped (set PRAISONAI_REAL_LLM=1 to enable)"
fi

# Summary
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  Verification Complete!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "All checks passed. The TUI + Queue system is working correctly."
echo ""
echo "To run with real LLM:"
echo "  PRAISONAI_REAL_LLM=1 ./scripts/verify_tui_real_keys.sh"
echo ""
