#!/usr/bin/env python3
"""
SDK Example: Submit, Poll, and Get Result for Async Jobs

This example demonstrates how to use the PraisonAI Jobs SDK to:
1. Submit an async job
2. Poll for status
3. Get the result

Requirements:
- OPENAI_API_KEY environment variable set
- Jobs server running on http://127.0.0.1:8005

Usage:
    python sdk_submit_poll_result.py
"""

import os
import time
import httpx

# Configuration
API_URL = os.getenv("PRAISONAI_BASE_URL", "http://127.0.0.1:8005")
POLL_INTERVAL = 2  # seconds


def submit_job(prompt: str, idempotency_key: str = None) -> dict:
    """Submit a job and return the response."""
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{API_URL}/api/v1/runs",
            json={"prompt": prompt},
            headers=headers if headers else None
        )
        response.raise_for_status()
        return response.json()


def get_status(job_id: str) -> dict:
    """Get job status."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{API_URL}/api/v1/runs/{job_id}")
        response.raise_for_status()
        return response.json()


def get_result(job_id: str) -> dict:
    """Get job result."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{API_URL}/api/v1/runs/{job_id}/result")
        response.raise_for_status()
        return response.json()


def wait_for_completion(job_id: str, max_wait: int = 120) -> dict:
    """Poll until job completes."""
    start = time.time()
    while time.time() - start < max_wait:
        status = get_status(job_id)
        print(f"  Status: {status['status']} | Progress: {status['progress']['percentage']:.0f}%")
        
        if status["status"] in ("succeeded", "failed", "cancelled"):
            return status
        
        # Honor retry_after if present
        wait_time = status.get("retry_after") or POLL_INTERVAL
        time.sleep(wait_time)
    
    raise TimeoutError(f"Job {job_id} did not complete within {max_wait}s")


def main():
    print("=" * 60)
    print("PraisonAI Async Jobs SDK Example")
    print("=" * 60)
    
    # Check if server is running
    try:
        with httpx.Client(timeout=5.0) as client:
            health = client.get(f"{API_URL}/health")
            health.raise_for_status()
            print(f"✓ Server healthy: {health.json()['status']}")
    except Exception as e:
        print(f"✗ Server not available at {API_URL}: {e}")
        print("  Start the server with: python -m uvicorn praisonai.jobs.server:create_app --port 8005 --factory")
        return
    
    # 1. Submit a job
    print("\n1. Submitting job...")
    prompt = "What is the capital of France? Answer in one word."
    result = submit_job(prompt)
    job_id = result["job_id"]
    print(f"   Job ID: {job_id}")
    print(f"   Status: {result['status']}")
    print(f"   Poll URL: {result['poll_url']}")
    
    # 2. Wait for completion
    print("\n2. Waiting for completion...")
    final_status = wait_for_completion(job_id)
    print(f"   Final status: {final_status['status']}")
    
    # 3. Get result
    if final_status["status"] == "succeeded":
        print("\n3. Getting result...")
        result = get_result(job_id)
        print(f"   Result: {result['result']}")
        print(f"   Duration: {result['duration_seconds']:.2f}s")
    else:
        print(f"\n3. Job did not succeed: {final_status.get('error', 'Unknown error')}")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
