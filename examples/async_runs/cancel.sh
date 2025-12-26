#!/bin/bash
# CLI Example: Cancel a Running Job
#
# This example demonstrates how to cancel a running job.
#
# Requirements:
# - Jobs server running on http://127.0.0.1:8005
#
# Usage:
#     bash cancel.sh

set -e

API_URL="${PRAISONAI_BASE_URL:-http://127.0.0.1:8005}"

echo "============================================================"
echo "PraisonAI Job Cancellation Example"
echo "============================================================"

# Submit a long-running job
echo ""
echo "1. Submitting a job..."
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Write a detailed essay about the history of computing."}')

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "   Job ID: $JOB_ID"

# Wait briefly
echo ""
echo "2. Waiting 1 second..."
sleep 1

# Cancel the job
echo ""
echo "3. Cancelling job..."
CANCEL_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/runs/$JOB_ID/cancel")
STATUS=$(echo "$CANCEL_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "   Status after cancel: $STATUS"

# Verify cancellation
echo ""
echo "4. Verification:"
if [ "$STATUS" = "cancelled" ]; then
    echo "   ✓ SUCCESS: Job was cancelled"
else
    echo "   ℹ Job status: $STATUS (may have completed before cancel)"
fi

echo ""
echo "============================================================"
echo "Cancellation example completed!"
echo "============================================================"
