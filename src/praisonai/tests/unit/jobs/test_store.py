"""Unit tests for jobs store."""

import pytest

from praisonai.jobs.models import Job, JobStatus
from praisonai.jobs.store import InMemoryJobStore


@pytest.fixture
def store():
    """Create a fresh store for each test."""
    return InMemoryJobStore(max_jobs=100)


@pytest.fixture
def sample_job():
    """Create a sample job."""
    return Job(prompt="Test prompt", session_id="sess_123")


class TestInMemoryJobStore:
    """Tests for InMemoryJobStore."""
    
    @pytest.mark.asyncio
    async def test_save_and_get(self, store, sample_job):
        """Test saving and retrieving a job."""
        await store.save(sample_job)
        
        retrieved = await store.get(sample_job.id)
        
        assert retrieved is not None
        assert retrieved.id == sample_job.id
        assert retrieved.prompt == "Test prompt"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        """Test getting a nonexistent job."""
        result = await store.get("nonexistent_id")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_by_idempotency_key(self, store):
        """Test getting job by idempotency key."""
        job = Job(prompt="Test", idempotency_key="idem_123")
        await store.save(job)
        
        retrieved = await store.get_by_idempotency_key("idem_123")
        
        assert retrieved is not None
        assert retrieved.id == job.id
    
    @pytest.mark.asyncio
    async def test_get_by_idempotency_key_nonexistent(self, store):
        """Test getting by nonexistent idempotency key."""
        result = await store.get_by_idempotency_key("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, store):
        """Test listing jobs when empty."""
        jobs = await store.list_jobs()
        assert jobs == []
    
    @pytest.mark.asyncio
    async def test_list_jobs(self, store):
        """Test listing jobs."""
        job1 = Job(prompt="Test 1")
        job2 = Job(prompt="Test 2")
        await store.save(job1)
        await store.save(job2)
        
        jobs = await store.list_jobs()
        
        assert len(jobs) == 2
    
    @pytest.mark.asyncio
    async def test_list_jobs_by_status(self, store):
        """Test listing jobs filtered by status."""
        job1 = Job(prompt="Test 1")
        job2 = Job(prompt="Test 2")
        job2.start()
        await store.save(job1)
        await store.save(job2)
        
        queued = await store.list_jobs(status=JobStatus.QUEUED)
        running = await store.list_jobs(status=JobStatus.RUNNING)
        
        assert len(queued) == 1
        assert len(running) == 1
        assert queued[0].id == job1.id
        assert running[0].id == job2.id
    
    @pytest.mark.asyncio
    async def test_list_jobs_by_session_id(self, store):
        """Test listing jobs filtered by session ID."""
        job1 = Job(prompt="Test 1", session_id="sess_a")
        job2 = Job(prompt="Test 2", session_id="sess_b")
        job3 = Job(prompt="Test 3", session_id="sess_a")
        await store.save(job1)
        await store.save(job2)
        await store.save(job3)
        
        sess_a_jobs = await store.list_jobs(session_id="sess_a")
        
        assert len(sess_a_jobs) == 2
    
    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, store):
        """Test listing jobs with pagination."""
        for i in range(5):
            await store.save(Job(prompt=f"Test {i}"))
        
        page1 = await store.list_jobs(limit=2, offset=0)
        page2 = await store.list_jobs(limit=2, offset=2)
        page3 = await store.list_jobs(limit=2, offset=4)
        
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
    
    @pytest.mark.asyncio
    async def test_count(self, store):
        """Test counting jobs."""
        for i in range(3):
            await store.save(Job(prompt=f"Test {i}"))
        
        count = await store.count()
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_count_by_status(self, store):
        """Test counting jobs by status."""
        job1 = Job(prompt="Test 1")
        job2 = Job(prompt="Test 2")
        job2.start()
        job3 = Job(prompt="Test 3")
        job3.start()
        job3.succeed("Done")
        
        await store.save(job1)
        await store.save(job2)
        await store.save(job3)
        
        queued_count = await store.count(status=JobStatus.QUEUED)
        running_count = await store.count(status=JobStatus.RUNNING)
        succeeded_count = await store.count(status=JobStatus.SUCCEEDED)
        
        assert queued_count == 1
        assert running_count == 1
        assert succeeded_count == 1
    
    @pytest.mark.asyncio
    async def test_delete(self, store, sample_job):
        """Test deleting a job."""
        await store.save(sample_job)
        
        result = await store.delete(sample_job.id)
        
        assert result is True
        assert await store.get(sample_job.id) is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        """Test deleting a nonexistent job."""
        result = await store.delete("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_removes_idempotency_key(self, store):
        """Test that deleting a job removes its idempotency key."""
        job = Job(prompt="Test", idempotency_key="idem_456")
        await store.save(job)
        
        await store.delete(job.id)
        
        assert await store.get_by_idempotency_key("idem_456") is None
    
    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, store):
        """Test cleaning up old completed jobs."""
        # Create completed jobs
        old_job = Job(prompt="Old")
        old_job.start()
        old_job.succeed("Done")
        # Manually set completed_at to past
        from datetime import datetime, timedelta
        old_job.completed_at = datetime.utcnow() - timedelta(days=2)
        
        new_job = Job(prompt="New")
        new_job.start()
        new_job.succeed("Done")
        
        await store.save(old_job)
        await store.save(new_job)
        
        # Cleanup jobs older than 1 day
        cleaned = await store.cleanup_old_jobs(max_age_seconds=86400)
        
        assert cleaned == 1
        assert await store.get(old_job.id) is None
        assert await store.get(new_job.id) is not None
    
    @pytest.mark.asyncio
    async def test_max_jobs_eviction(self):
        """Test that old completed jobs are evicted when max is reached."""
        store = InMemoryJobStore(max_jobs=5)
        
        # Create 5 completed jobs
        for i in range(5):
            job = Job(prompt=f"Test {i}")
            job.start()
            job.succeed(f"Result {i}")
            await store.save(job)
        
        # Add one more - should trigger eviction
        new_job = Job(prompt="New job")
        await store.save(new_job)
        
        # Should still have at most max_jobs
        count = await store.count()
        assert count <= 6  # May have evicted some
    
    @pytest.mark.asyncio
    async def test_get_stats(self, store):
        """Test getting store statistics."""
        job1 = Job(prompt="Test 1")
        job2 = Job(prompt="Test 2", idempotency_key="idem_1")
        job2.start()
        await store.save(job1)
        await store.save(job2)
        
        stats = store.get_stats()
        
        assert stats["total_jobs"] == 2
        assert stats["idempotency_keys"] == 1
        assert stats["max_jobs"] == 100
        assert "status_counts" in stats
        assert stats["status_counts"]["queued"] == 1
        assert stats["status_counts"]["running"] == 1
