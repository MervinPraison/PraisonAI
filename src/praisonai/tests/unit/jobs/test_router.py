"""Integration tests for jobs router."""

import pytest
from fastapi.testclient import TestClient

from praisonai.jobs.server import create_app
from praisonai.jobs.store import InMemoryJobStore
from praisonai.jobs.executor import JobExecutor


@pytest.fixture
def store():
    """Create a fresh store for each test."""
    return InMemoryJobStore(max_jobs=100)


@pytest.fixture
def executor(store):
    """Create executor with the store."""
    return JobExecutor(store=store, max_concurrent=5)


@pytest.fixture
def client(store, executor):
    """Create test client."""
    app = create_app(store=store, executor=executor)
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health endpoint."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "store" in data
        assert "executor_stats" in data


class TestStatsEndpoint:
    """Tests for stats endpoint."""
    
    def test_get_stats(self, client):
        """Test stats endpoint."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "executor" in data


class TestSubmitEndpoint:
    """Tests for job submission."""
    
    def test_submit_job(self, client):
        """Test submitting a job."""
        response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("run_")
        assert data["status"] == "queued"
        assert "poll_url" in data
        assert "stream_url" in data
    
    def test_submit_job_with_all_fields(self, client):
        """Test submitting a job with all fields."""
        response = client.post(
            "/api/v1/runs",
            json={
                "prompt": "Test prompt",
                "agent_file": "agents.yaml",
                "framework": "crewai",
                "timeout": 1800,
                "session_id": "sess_123"
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
    
    def test_submit_job_idempotency(self, client):
        """Test idempotency key prevents duplicate jobs."""
        # First submission
        response1 = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"},
            headers={"Idempotency-Key": "idem_test_123"}
        )
        assert response1.status_code == 202
        job_id1 = response1.json()["job_id"]
        
        # Second submission with same key
        response2 = client.post(
            "/api/v1/runs",
            json={"prompt": "Different prompt"},
            headers={"Idempotency-Key": "idem_test_123"}
        )
        assert response2.status_code == 202
        job_id2 = response2.json()["job_id"]
        
        # Should return the same job
        assert job_id1 == job_id2


class TestStatusEndpoint:
    """Tests for job status."""
    
    def test_get_status(self, client):
        """Test getting job status."""
        # Submit a job first
        submit_response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        job_id = submit_response.json()["job_id"]
        
        # Get status
        response = client.get(f"/api/v1/runs/{job_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "progress" in data
    
    def test_get_status_not_found(self, client):
        """Test getting status of nonexistent job."""
        response = client.get("/api/v1/runs/nonexistent_id")
        
        assert response.status_code == 404


class TestListEndpoint:
    """Tests for listing jobs."""
    
    def test_list_jobs_empty(self, client):
        """Test listing jobs when empty."""
        response = client.get("/api/v1/runs")
        
        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0
    
    def test_list_jobs(self, client):
        """Test listing jobs."""
        # Submit some jobs
        client.post("/api/v1/runs", json={"prompt": "Test 1"})
        client.post("/api/v1/runs", json={"prompt": "Test 2"})
        
        response = client.get("/api/v1/runs")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["total"] == 2
    
    def test_list_jobs_with_status_filter(self, client):
        """Test listing jobs with status filter."""
        # Submit a job
        client.post("/api/v1/runs", json={"prompt": "Test"})
        
        # Jobs may transition quickly, just verify the endpoint works
        response = client.get("/api/v1/runs?status=queued")
        assert response.status_code == 200
        
        # Also test with other statuses
        response = client.get("/api/v1/runs?status=running")
        assert response.status_code == 200
        
        response = client.get("/api/v1/runs?status=failed")
        assert response.status_code == 200
    
    def test_list_jobs_pagination(self, client):
        """Test listing jobs with pagination."""
        # Submit 5 jobs
        for i in range(5):
            client.post("/api/v1/runs", json={"prompt": f"Test {i}"})
        
        # Get first page
        response = client.get("/api/v1/runs?page=1&page_size=2")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestResultEndpoint:
    """Tests for job results."""
    
    def test_get_result_job_lifecycle(self, client):
        """Test getting result follows job lifecycle."""
        # Submit a job
        submit_response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        job_id = submit_response.json()["job_id"]
        
        # Result endpoint should work (may return 409 if not complete, or 200 if complete/failed)
        response = client.get(f"/api/v1/runs/{job_id}/result")
        
        # Either 200 (completed) or 409 (not complete) is valid
        assert response.status_code in (200, 409)
    
    def test_get_result_not_found(self, client):
        """Test getting result of nonexistent job."""
        response = client.get("/api/v1/runs/nonexistent_id/result")
        
        assert response.status_code == 404


class TestCancelEndpoint:
    """Tests for job cancellation."""
    
    def test_cancel_job(self, client):
        """Test cancelling a job."""
        # Submit a job
        submit_response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        job_id = submit_response.json()["job_id"]
        
        # Cancel the job - may succeed (200) or fail if job already completed (409)
        response = client.post(f"/api/v1/runs/{job_id}/cancel")
        
        # Either 200 (cancelled) or 409 (already complete) is valid due to async execution
        assert response.status_code in (200, 409)
    
    def test_cancel_job_not_found(self, client):
        """Test cancelling nonexistent job."""
        response = client.post("/api/v1/runs/nonexistent_id/cancel")
        
        assert response.status_code == 404


class TestDeleteEndpoint:
    """Tests for job deletion."""
    
    def test_delete_job_lifecycle(self, client):
        """Test deleting a job follows lifecycle rules."""
        # Submit a job
        submit_response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        job_id = submit_response.json()["job_id"]
        
        # Try to delete - may fail (409) if running, or succeed (204) if already complete
        response = client.delete(f"/api/v1/runs/{job_id}")
        
        # Either 204 (deleted) or 409 (still running) is valid
        assert response.status_code in (204, 409)
    
    def test_delete_cancelled_job(self, client):
        """Test deleting a cancelled job."""
        # Submit and cancel a job
        submit_response = client.post(
            "/api/v1/runs",
            json={"prompt": "Test prompt"}
        )
        job_id = submit_response.json()["job_id"]
        client.post(f"/api/v1/runs/{job_id}/cancel")
        
        # Delete the job
        response = client.delete(f"/api/v1/runs/{job_id}")
        
        assert response.status_code == 204
        
        # Verify it's gone
        get_response = client.get(f"/api/v1/runs/{job_id}")
        assert get_response.status_code == 404
    
    def test_delete_not_found(self, client):
        """Test deleting nonexistent job."""
        response = client.delete("/api/v1/runs/nonexistent_id")
        
        assert response.status_code == 404
