"""Unit tests for jobs models."""

from praisonai.jobs.models import (
    Job,
    JobStatus,
    JobSubmitRequest,
    JobStatusResponse,
    JobResultResponse,
    JobProgress,
    JobListResponse
)


class TestJobStatus:
    """Tests for JobStatus enum."""
    
    def test_status_values(self):
        """Test all status values exist."""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCEEDED.value == "succeeded"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"
    
    def test_status_is_string_enum(self):
        """Test status can be used as string."""
        assert str(JobStatus.RUNNING) == "JobStatus.RUNNING"
        assert JobStatus.RUNNING.value == "running"


class TestJob:
    """Tests for Job model."""
    
    def test_job_creation_defaults(self):
        """Test job creation with defaults."""
        job = Job(prompt="Test prompt")
        
        assert job.prompt == "Test prompt"
        assert job.status == JobStatus.QUEUED
        assert job.id.startswith("run_")
        assert job.framework == "praisonai"
        assert job.timeout == 3600
        assert job.progress_percentage == 0.0
        assert job.created_at is not None
        assert job.started_at is None
        assert job.completed_at is None
    
    def test_job_creation_with_all_fields(self):
        """Test job creation with all fields."""
        job = Job(
            prompt="Test prompt",
            agent_file="agents.yaml",
            agent_yaml="agents:\n  - name: test",
            framework="crewai",
            config={"key": "value"},
            webhook_url="https://example.com/webhook",
            timeout=7200,
            session_id="session_123",
            idempotency_key="idem_456"
        )
        
        assert job.agent_file == "agents.yaml"
        assert job.agent_yaml == "agents:\n  - name: test"
        assert job.framework == "crewai"
        assert job.config == {"key": "value"}
        assert job.webhook_url == "https://example.com/webhook"
        assert job.timeout == 7200
        assert job.session_id == "session_123"
        assert job.idempotency_key == "idem_456"
    
    def test_job_start(self):
        """Test job start method."""
        job = Job(prompt="Test")
        assert job.status == JobStatus.QUEUED
        assert job.started_at is None
        
        job.start()
        
        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None
    
    def test_job_succeed(self):
        """Test job succeed method."""
        job = Job(prompt="Test")
        job.start()
        
        job.succeed("Result data", {"tokens": 100})
        
        assert job.status == JobStatus.SUCCEEDED
        assert job.result == "Result data"
        assert job.metrics == {"tokens": 100}
        assert job.completed_at is not None
        assert job.progress_percentage == 100.0
    
    def test_job_fail(self):
        """Test job fail method."""
        job = Job(prompt="Test")
        job.start()
        
        job.fail("Something went wrong")
        
        assert job.status == JobStatus.FAILED
        assert job.error == "Something went wrong"
        assert job.completed_at is not None
    
    def test_job_cancel(self):
        """Test job cancel method."""
        job = Job(prompt="Test")
        job.start()
        
        job.cancel()
        
        assert job.status == JobStatus.CANCELLED
        assert job.completed_at is not None
    
    def test_job_is_terminal(self):
        """Test is_terminal property."""
        job = Job(prompt="Test")
        assert not job.is_terminal
        
        job.start()
        assert not job.is_terminal
        
        job.succeed("Done")
        assert job.is_terminal
    
    def test_job_is_terminal_failed(self):
        """Test is_terminal for failed job."""
        job = Job(prompt="Test")
        job.start()
        job.fail("Error")
        assert job.is_terminal
    
    def test_job_is_terminal_cancelled(self):
        """Test is_terminal for cancelled job."""
        job = Job(prompt="Test")
        job.start()
        job.cancel()
        assert job.is_terminal
    
    def test_job_duration_seconds(self):
        """Test duration_seconds property."""
        job = Job(prompt="Test")
        assert job.duration_seconds is None
        
        job.start()
        # Duration should be very small but not None
        assert job.duration_seconds is not None
        assert job.duration_seconds >= 0
    
    def test_job_update_progress(self):
        """Test update_progress method."""
        job = Job(prompt="Test")
        
        job.update_progress(percentage=50.0, step="Processing")
        
        assert job.progress_percentage == 50.0
        assert job.progress_step == "Processing"
    
    def test_job_update_progress_clamps_values(self):
        """Test update_progress clamps percentage to 0-100."""
        job = Job(prompt="Test")
        
        job.update_progress(percentage=150.0)
        assert job.progress_percentage == 100.0
        
        job.update_progress(percentage=-10.0)
        assert job.progress_percentage == 0.0
    
    def test_job_to_status_response(self):
        """Test to_status_response method."""
        job = Job(prompt="Test", session_id="sess_123")
        job.start()
        job.update_progress(percentage=50.0, step="Working")
        
        response = job.to_status_response()
        
        assert isinstance(response, JobStatusResponse)
        assert response.job_id == job.id
        assert response.status == JobStatus.RUNNING
        assert response.progress.percentage == 50.0
        assert response.progress.current_step == "Working"
        assert response.session_id == "sess_123"
        assert response.retry_after == 5  # Running jobs suggest 5s retry
    
    def test_job_to_result_response(self):
        """Test to_result_response method."""
        job = Job(prompt="Test")
        job.start()
        job.succeed("Final result", {"tokens": 200})
        
        response = job.to_result_response()
        
        assert isinstance(response, JobResultResponse)
        assert response.job_id == job.id
        assert response.status == JobStatus.SUCCEEDED
        assert response.result == "Final result"
        assert response.metrics == {"tokens": 200}
        assert response.duration_seconds is not None


class TestJobSubmitRequest:
    """Tests for JobSubmitRequest model."""
    
    def test_submit_request_minimal(self):
        """Test minimal submit request."""
        request = JobSubmitRequest(prompt="Do something")
        
        assert request.prompt == "Do something"
        assert request.framework == "praisonai"
        assert request.timeout == 3600
    
    def test_submit_request_full(self):
        """Test full submit request."""
        request = JobSubmitRequest(
            prompt="Do something",
            agent_file="agents.yaml",
            framework="crewai",
            webhook_url="https://example.com/hook",
            timeout=1800,
            session_id="sess_abc",
            idempotency_key="idem_xyz"
        )
        
        assert request.agent_file == "agents.yaml"
        assert request.framework == "crewai"
        assert request.webhook_url == "https://example.com/hook"
        assert request.timeout == 1800
        assert request.session_id == "sess_abc"
        assert request.idempotency_key == "idem_xyz"


class TestJobProgress:
    """Tests for JobProgress model."""
    
    def test_progress_defaults(self):
        """Test progress defaults."""
        progress = JobProgress()
        
        assert progress.percentage == 0.0
        assert progress.current_step is None
        assert progress.steps_completed == 0
        assert progress.steps_total is None
    
    def test_progress_with_values(self):
        """Test progress with values."""
        progress = JobProgress(
            percentage=75.0,
            current_step="Analyzing",
            steps_completed=3,
            steps_total=4
        )
        
        assert progress.percentage == 75.0
        assert progress.current_step == "Analyzing"
        assert progress.steps_completed == 3
        assert progress.steps_total == 4


class TestJobListResponse:
    """Tests for JobListResponse model."""
    
    def test_list_response(self):
        """Test list response."""
        job1 = Job(prompt="Test 1")
        job2 = Job(prompt="Test 2")
        
        response = JobListResponse(
            jobs=[job1.to_status_response(), job2.to_status_response()],
            total=2,
            page=1,
            page_size=20
        )
        
        assert len(response.jobs) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 20
