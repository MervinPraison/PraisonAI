#!/bin/bash
# CLI Example: SSE Streaming
#
# This example demonstrates how to stream job progress via Server-Sent Events.
#
# Requirements:
# - Jobs server running on http://127.0.0.1:8005
#
# Usage:
#     bash sse_stream.sh

set -e

API_URL="${PRAISONAI_BASE_URL:-http://127.0.0.1:8005}"

echo "============================================================"
echo "PraisonAI SSE Streaming Example"
echo "============================================================"

# Submit a job
echo ""
echo "1. Submitting job..."
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Count from 1 to 5."}')

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "   Job ID: $JOB_ID"

# Stream progress
echo ""
echo "2. Streaming progress (Ctrl+C to stop)..."
echo "   Connecting to: $API_URL/api/v1/runs/$JOB_ID/stream"
echo ""

# Use curl to stream SSE events (timeout after 60s)
curl -s -N --max-time 60 "$API_URL/api/v1/runs/$JOB_ID/stream" | while read -r line; do
    if [[ "$line" == data:* ]]; then
        data="${line#data: }"
        if [ "$data" = "[DONE]" ]; then
            echo "   Stream completed"
            break
        fi
        echo "   Event: $data"
    fi
done

echo ""
echo "============================================================"
echo "Streaming example completed!"
echo "============================================================"
