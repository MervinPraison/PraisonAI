"""
Unit tests for scheduler incident tracking.

Tests:
- error_signature / normalise_error stability and grouping
- Incident dataclass serialization round-trip
- IncidentTracker latching: alert once, dedupe, changed-error re-alert,
  recovery on success, and N-consecutive-failure threshold
- Exports from praisonaiagents.scheduler
"""

from praisonaiagents.scheduler.models import RunRecord
from praisonaiagents.scheduler.incidents import (
    Incident,
    IncidentTracker,
    error_signature,
    normalise_error,
)


def _failed(error, job_id="j1", job_name="Nightly", ts=100.0):
    return RunRecord(
        job_id=job_id, job_name=job_name, status="failed", error=error, timestamp=ts
    )


def _ok(job_id="j1", job_name="Nightly", ts=200.0):
    return RunRecord(job_id=job_id, job_name=job_name, status="succeeded", timestamp=ts)


class TestErrorSignature:
    def test_same_cause_same_signature(self):
        a = error_signature("429 rate limit (req id 0xabc123def456)")
        b = error_signature("429 rate limit (req id 0x99900012345a)")
        assert a == b

    def test_different_cause_different_signature(self):
        assert error_signature("429 rate limit") != error_signature("500 server error")

    def test_normalise_strips_hex_and_volatile_ids(self):
        # Hex blobs / uuids / long digit runs (request ids, timestamps, pids)
        # are volatile and must collapse so a retry does not re-alert.
        assert normalise_error("boom 0xDEADBEEF") == normalise_error("boom 0xCAFEBABE")
        assert normalise_error("failed at 1700000001") == normalise_error(
            "failed at 1700009999"
        )
        assert normalise_error("worker7 crashed") == normalise_error("worker3 crashed")

    def test_distinct_numeric_codes_keep_distinct_signature(self):
        # A short standalone number is a meaningful *category* (HTTP status,
        # error/exit code): different codes must NOT collapse, else the promised
        # re-alert on a changed failure is suppressed (regression: Greptile P1).
        assert error_signature("HTTP 404 not found") != error_signature(
            "HTTP 500 server error"
        )
        assert error_signature("error code 404") != error_signature("error code 500")
        assert error_signature("exited with code 12") != error_signature(
            "exited with code 34"
        )

    def test_same_code_changing_id_still_groups(self):
        # Same category code with a changing request id stays one incident.
        assert error_signature("429 rate limit req abc12345678") == error_signature(
            "429 rate limit req def87654321"
        )

    def test_signature_is_hex_sha256(self):
        sig = error_signature("boom")
        assert len(sig) == 64
        int(sig, 16)  # parses as hex


class TestIncidentModel:
    def test_round_trip(self):
        inc = Incident(
            job_id="j1",
            signature="sig",
            state="alerted",
            error="boom",
            count=3,
            job_name="Nightly",
        )
        restored = Incident.from_dict(inc.to_dict())
        assert restored == inc


class TestIncidentTrackerDefault:
    def test_alert_once_then_dedupe(self):
        tracker = IncidentTracker()
        state = {}
        first = tracker.observe(_failed("429 rate limit"), state)
        assert first is not None
        assert first.state == "alerted"
        assert first.job_name == "Nightly"
        # Identical failure again → no re-alert.
        assert tracker.observe(_failed("429 rate limit"), state) is None
        assert tracker.observe(_failed("429 rate limit"), state) is None

    def test_changed_error_re_alerts(self):
        tracker = IncidentTracker()
        state = {}
        assert tracker.observe(_failed("429 rate limit"), state) is not None
        assert tracker.observe(_failed("429 rate limit"), state) is None
        second = tracker.observe(_failed("500 server error"), state)
        assert second is not None
        assert second.state == "alerted"

    def test_changed_status_code_re_alerts(self):
        # Failures differing only by a meaningful numeric code (404 → 500) must
        # be treated as distinct incidents and re-alert (Greptile P1 regression).
        tracker = IncidentTracker()
        state = {}
        assert tracker.observe(_failed("HTTP 404 not found"), state) is not None
        assert tracker.observe(_failed("HTTP 404 not found"), state) is None
        second = tracker.observe(_failed("HTTP 500 server error"), state)
        assert second is not None
        assert second.state == "alerted"

    def test_recovery_closes_incident(self):
        tracker = IncidentTracker()
        state = {}
        assert tracker.observe(_failed("boom"), state) is not None
        recovered = tracker.observe(_ok(), state)
        assert recovered is not None
        assert recovered.state == "resolved"
        # After recovery a new failure of the same signature re-alerts.
        again = tracker.observe(_failed("boom"), state)
        assert again is not None
        assert again.state == "alerted"

    def test_success_with_no_incident_is_noop(self):
        tracker = IncidentTracker()
        state = {}
        assert tracker.observe(_ok(), state) is None

    def test_skipped_and_no_change_are_ignored(self):
        tracker = IncidentTracker()
        state = {}
        assert (
            tracker.observe(
                RunRecord(job_id="j1", status="skipped"), state
            )
            is None
        )
        assert (
            tracker.observe(
                RunRecord(job_id="j1", status="no_change"), state
            )
            is None
        )


class TestIncidentTrackerThreshold:
    def test_alert_only_after_n_consecutive(self):
        tracker = IncidentTracker(after_failures=3)
        state = {}
        assert tracker.observe(_failed("boom", ts=1), state) is None
        assert tracker.observe(_failed("boom", ts=2), state) is None
        third = tracker.observe(_failed("boom", ts=3), state)
        assert third is not None
        assert third.state == "alerted"
        assert third.count == 3
        # No re-alert after the threshold crossing.
        assert tracker.observe(_failed("boom", ts=4), state) is None

    def test_subthreshold_blip_no_recovery_note(self):
        tracker = IncidentTracker(after_failures=3)
        state = {}
        assert tracker.observe(_failed("boom", ts=1), state) is None
        # Recovers before threshold → never alerted → no recovery note.
        assert tracker.observe(_ok(ts=2), state) is None

    def test_below_one_treated_as_one(self):
        tracker = IncidentTracker(after_failures=0)
        assert tracker.after_failures == 1
        assert tracker.observe(_failed("boom"), {}) is not None


class TestExports:
    def test_public_exports(self):
        import praisonaiagents.scheduler as sched

        assert sched.IncidentTracker is IncidentTracker
        assert sched.Incident is Incident
        assert sched.error_signature is error_signature
        assert sched.normalise_error is normalise_error
