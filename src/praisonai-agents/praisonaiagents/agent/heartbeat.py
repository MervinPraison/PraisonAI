"""Heartbeat — runs an agent on a schedule, delivers results via callback.

Standalone wrapper class. Does NOT modify the Agent class.

Usage::

    from praisonaiagents import Agent, Heartbeat

    agent = Agent(instructions="Check server status")
    hb = Heartbeat(agent, schedule="every 30m", prompt="Report status")
    hb.start()   # blocking loop
    # hb.start(blocking=False)  # background thread
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatConfig:
    """Configuration for Heartbeat scheduler.

    Attributes:
        schedule: Human-friendly schedule expression. Supports:
            - Keywords: "hourly", "daily", "weekly"
            - Intervals: "every 30m", "every 6h", "*/30m", "*/10s"
            - Cron: "cron:0 7 * * *"
            - One-shot: "at:2026-03-01T09:00:00"
        prompt: Override prompt sent to agent each tick. None = use agent's default.
        on_result: Callback receiving (result_text: str). Default: log to stdout.
        on_error: "retry" | "skip" | callable(error). Default: "retry".
        max_retries: Max consecutive retries before skipping. Default: 3.
    """
    schedule: str = "hourly"
    prompt: Optional[str] = None
    on_result: Optional[Callable] = None
    on_error: Union[str, Callable] = "retry"
    max_retries: int = 3


class Heartbeat:
    """Standalone heartbeat coordinator.

    Runs an Agent on a schedule and delivers results via callback.
    Does NOT add any params to the Agent class.

    Usage::

        from praisonaiagents import Agent, Heartbeat

        agent = Agent(instructions="Monitor server health")
        hb = Heartbeat(agent, schedule="hourly")
        hb.start()
    """

    def __init__(
        self,
        agent,
        schedule: str = "hourly",
        prompt: Optional[str] = None,
        on_result: Optional[Callable] = None,
        on_error: Union[str, Callable] = "retry",
        max_retries: int = 3,
    ):
        self.agent = agent
        self.config = HeartbeatConfig(
            schedule=schedule,
            prompt=prompt,
            on_result=on_result,
            on_error=on_error,
            max_retries=max_retries,
        )
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval_seconds = self._resolve_interval(schedule)

    def start(self, blocking: bool = True) -> None:
        """Start the heartbeat loop.

        Args:
            blocking: If True, blocks the calling thread. If False,
                      runs in a background daemon thread.
        """
        self._running = True
        if blocking:
            self._loop()
        else:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ── internals ────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Main polling loop."""
        retries = 0
        while self._running:
            try:
                result = self._tick()
                retries = 0  # Reset on success
                self._deliver(result)
            except Exception as e:
                retries += 1
                logger.error(f"[heartbeat] {self.agent.name}: error on tick #{retries}: {e}")
                if callable(self.config.on_error):
                    self.config.on_error(e)
                elif self.config.on_error == "skip":
                    logger.warning(f"[heartbeat] Skipping error: {e}")
                else:  # "retry"
                    if retries >= self.config.max_retries:
                        logger.error(
                            f"[heartbeat] {self.agent.name}: max retries "
                            f"({self.config.max_retries}) reached, skipping."
                        )
                        retries = 0
            time.sleep(self._interval_seconds)

    def _tick(self) -> str:
        """Execute one heartbeat tick — run the agent and return result."""
        prompt = self.config.prompt or "Run your scheduled check."
        result = self.agent.start(prompt)
        return str(result) if result else ""

    def _deliver(self, result: str) -> None:
        """Deliver result via callback or log."""
        if self.config.on_result:
            self.config.on_result(result)
        else:
            logger.info(f"[heartbeat] {self.agent.name}: {result[:200]}")

    @staticmethod
    def _resolve_interval(schedule: str) -> float:
        """Convert schedule string to interval in seconds.

        Uses the scheduler parser if available, otherwise falls back to
        simple keyword parsing.
        """
        try:
            from ..scheduler.parser import parse_schedule
            sched = parse_schedule(schedule)
            if sched.every_seconds:
                return float(sched.every_seconds)
        except (ImportError, Exception):
            pass

        # Fallback keyword resolution
        keywords = {
            "hourly": 3600,
            "daily": 86400,
            "weekly": 604800,
        }
        lower = schedule.lower().strip()
        if lower in keywords:
            return float(keywords[lower])

        # Try parsing "every Xm/h/s" patterns
        import re
        match = re.match(r"(?:every\s+)?(\d+)\s*(s|m|h)", lower)
        if match:
            val, unit = int(match.group(1)), match.group(2)
            multipliers = {"s": 1, "m": 60, "h": 3600}
            return float(val * multipliers.get(unit, 60))

        return 3600.0  # Default to hourly
