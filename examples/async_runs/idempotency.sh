#!/bin/bash
# CLI Example: Idempotency Key Usage
#
# This example demonstrates how idempotency keys prevent duplicate job submissions.
# Submitting the same request with the same idempotency key returns the existing job.
#
# Requirements:
# - Jobs server running on http://127.0.0.1:8005
#
# Usage:
#     bash idempotency.sh

set -e

API_URL="${PRAISONAI_BASE_URL:-http://127.0.0.1:8005}"
IDEM_KEY="example-idem-key-$(date +%s)"

echo "============================================================"
echo "PraisonAI Idempotency Key Example"
echo "============================================================"

# First submission
echo ""
echo "1. First submission with Idempotency-Key: $IDEM_KEY"
RESPONSE1=$(curl -s -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEM_KEY" \
    -d '{"prompt": "What is 1+1?"}')

JOB_ID1=$(echo "$RESPONSE1" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "   Job ID: $JOB_ID1"

# Second submission with same key
echo ""
echo "2. Second submission with SAME Idempotency-Key: $IDEM_KEY"
RESPONSE2=$(curl -s -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEM_KEY" \
    -d '{"prompt": "Different prompt but same key"}')

JOB_ID2=$(echo "$RESPONSE2" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "   Job ID: $JOB_ID2"

# Verify same job ID
echo ""
echo "3. Verification:"
if [ "$JOB_ID1" = "$JOB_ID2" ]; then
    echo "   ✓ SUCCESS: Same job ID returned (no duplicate created)"
else
    echo "   ✗ FAILURE: Different job IDs returned"
    exit 1
fi

echo ""
echo "============================================================"
echo "Idempotency example completed!"
echo "============================================================"
