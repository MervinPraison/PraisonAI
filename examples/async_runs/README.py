"""
Async Runs Examples
===================

This directory contains examples for the PraisonAI Async Jobs API.

Examples:
---------
1. sdk_submit_poll_result.py - Python SDK example for submit/poll/result
2. cli_submit_poll_result.sh - Bash/curl example for submit/poll/result
3. idempotency.sh - Demonstrates idempotency key usage
4. cancel.sh - Demonstrates job cancellation
5. sse_stream.sh - Demonstrates SSE streaming

Prerequisites:
--------------
1. Set OPENAI_API_KEY environment variable
2. Start the jobs server:
   
   cd /path/to/praisonai-package/src/praisonai
   python -m uvicorn praisonai.jobs.server:create_app --port 8005 --factory

3. Run examples:
   
   python sdk_submit_poll_result.py
   bash cli_submit_poll_result.sh
   bash idempotency.sh
   bash cancel.sh
   bash sse_stream.sh

Environment Variables:
----------------------
- OPENAI_API_KEY: Required for agent execution
- PRAISONAI_BASE_URL: API server URL (default: http://127.0.0.1:8005)
"""
