#!/usr/bin/env python3
"""
Recipe Async Jobs Example

This example demonstrates how to submit recipes as async jobs
to a jobs server with webhooks and idempotency.

Requirements:
    pip install praisonai httpx

Usage:
    1. Start the jobs server:
       python -m uvicorn praisonai.jobs.server:create_app --port 8005 --factory
    
    2. Run this example:
       python example_jobs.py
"""

import time


def main():
    """Submit and monitor an async job."""
    
    print("=" * 60)
    print("Recipe Async Jobs Example")
    print("=" * 60)
    
    # Import the jobs handler
    from praisonai.cli.features.jobs import JobsHandler
    
    # Create handler
    handler = JobsHandler(
        api_url="http://127.0.0.1:8005",
        verbose=True
    )
    
    print("\n1. Submitting job...")
    
    try:
        # Submit a job
        result = handler.submit(
            prompt="What are the key trends in AI for 2024?",
            framework="praisonai",
            timeout=300,
            wait=False,  # Don't wait, we'll poll manually
            output_json=False
        )
        
        job_id = result.get("job_id")
        print(f"   Job ID: {job_id}")
        print(f"   Status: {result.get('status')}")
        
        print("\n2. Polling for completion...")
        
        # Poll for completion
        max_polls = 60
        for i in range(max_polls):
            status_result = handler.status(job_id)
            status = status_result.get("status")
            progress = status_result.get("progress", 0)
            
            print(f"   [{i+1}/{max_polls}] Status: {status}, Progress: {progress}%")
            
            if status in ["succeeded", "failed", "cancelled"]:
                break
            
            time.sleep(5)
        
        print("\n3. Getting result...")
        
        # Get result
        result = handler.result(job_id)
        print(f"   Status: {result.get('status')}")
        
        if result.get("result"):
            output = str(result.get("result"))
            print(f"   Result preview: {output[:200]}...")
        
        print("\n4. Listing all jobs...")
        
        # List jobs
        handler.list_jobs(page=1, page_size=10)
        
    except Exception as e:
        print(f"\n   Error: {e}")
        print("\n   Make sure the jobs server is running:")
        print("   python -m uvicorn praisonai.jobs.server:create_app --port 8005 --factory")
    
    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
