#!/bin/bash
# CLI Example: Submit, Poll, and Get Result for Async Jobs
#
# This example demonstrates how to use the PraisonAI CLI to:
# 1. Submit an async job
# 2. Check job status
# 3. Get the result
#
# Requirements:
# - OPENAI_API_KEY environment variable set
# - Jobs server running on http://127.0.0.1:8005
#
# Usage:
#     bash cli_submit_poll_result.sh

set -e

API_URL="${PRAISONAI_BASE_URL:-http://127.0.0.1:8005}"

echo "============================================================"
echo "PraisonAI Async Jobs CLI Example"
echo "============================================================"

# Check if server is running
echo ""
echo "Checking server health..."
if ! curl -s "$API_URL/health" > /dev/null 2>&1; then
    echo "✗ Server not available at $API_URL"
    echo "  Start the server with: python -m uvicorn praisonai.jobs.server:create_app --port 8005 --factory"
    exit 1
fi
echo "✓ Server is healthy"

# 1. Submit a job
echo ""
echo "1. Submitting job..."
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "What is 2+2? Answer with just the number."}')

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "   Job ID: $JOB_ID"

# 2. Poll for status
echo ""
echo "2. Polling for status..."
while true; do
    STATUS_RESPONSE=$(curl -s "$API_URL/api/v1/runs/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['progress']['percentage'])")
    
    echo "   Status: $STATUS | Progress: ${PROGRESS}%"
    
    if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
        break
    fi
    
    sleep 2
done

# 3. Get result
echo ""
echo "3. Getting result..."
if [ "$STATUS" = "succeeded" ]; then
    RESULT=$(curl -s "$API_URL/api/v1/runs/$JOB_ID/result")
    echo "   Result: $(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])")"
    echo "   Duration: $(echo "$RESULT" | python3 -c "import sys,json; print(f\"{json.load(sys.stdin)['duration_seconds']:.2f}s\")")"
else
    echo "   Job did not succeed: $STATUS"
fi

echo ""
echo "============================================================"
echo "Example completed!"
echo "============================================================"
