"""Browser Agent Profiling Module.

Provides timing instrumentation and performance profiling for browser automation.

Usage:
    # Basic timing
    profiler = StepProfiler()
    with profiler.time("llm_decision"):
        result = await agent.process_observation(obs)
    
    # Get report
    print(profiler.get_report())

CLI:
    praisonai browser launch "goal" --profile         # Timing summary
    praisonai browser launch "goal" --deep-profile    # cProfile trace
"""

import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = logging.getLogger("praisonai.browser.profiling")


@dataclass
class TimingEntry:
    """Single timing measurement."""
    name: str
    duration: float
    step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepProfile:
    """Profile data for a single step."""
    step: int
    total_time: float = 0.0
    llm_time: float = 0.0
    screenshot_time: float = 0.0
    action_time: float = 0.0
    verify_time: float = 0.0
    stable_wait_time: float = 0.0
    screenshot_count: int = 0


class StepProfiler:
    """Profiler for browser automation steps.
    
    Tracks timing of key operations and provides summary reports.
    
    Example:
        profiler = StepProfiler(enabled=True)
        
        with profiler.step(0):
            with profiler.time("llm_decision"):
                action = agent.process(obs)
            with profiler.time("screenshot"):
                screenshot = capture()
        
        print(profiler.get_summary())
    """
    
    def __init__(self, enabled: bool = True, deep_profile: bool = False):
        """Initialize profiler.
        
        Args:
            enabled: Enable basic timing (--profile)
            deep_profile: Enable cProfile tracing (--deep-profile)
        """
        self.enabled = enabled
        self.deep_profile = deep_profile
        self._step_profiles: List[StepProfile] = []
        self._current_step: Optional[StepProfile] = None
        self._timings: List[TimingEntry] = []
        self._start_time: float = 0.0
        self._cprofile = None
        
        if deep_profile:
            self._init_cprofile()
    
    def _init_cprofile(self):
        """Lazily initialize cProfile."""
        try:
            import cProfile
            self._cprofile = cProfile.Profile()
        except ImportError:
            logger.warning("cProfile not available, deep profiling disabled")
            self.deep_profile = False
    
    def start(self):
        """Start profiling session."""
        self._start_time = time.perf_counter()
        if self._cprofile:
            self._cprofile.enable()
    
    def stop(self):
        """Stop profiling session."""
        if self._cprofile:
            self._cprofile.disable()
    
    @contextmanager
    def step(self, step_num: int):
        """Context manager for profiling a step.
        
        Args:
            step_num: Step number (0-indexed)
        """
        if not self.enabled:
            yield
            return
        
        step_start = time.perf_counter()
        self._current_step = StepProfile(step=step_num)
        
        try:
            yield self._current_step
        finally:
            self._current_step.total_time = time.perf_counter() - step_start
            self._step_profiles.append(self._current_step)
            self._current_step = None
    
    @contextmanager
    def time(self, operation: str):
        """Time a specific operation within current step.
        
        Args:
            operation: Name of operation (llm_decision, screenshot, action, verify, stable_wait)
        """
        if not self.enabled:
            yield
            return
        
        start = time.perf_counter()
        
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            
            # Record timing
            step_num = self._current_step.step if self._current_step else 0
            self._timings.append(TimingEntry(name=operation, duration=duration, step=step_num))
            
            # Update current step stats
            if self._current_step:
                if operation == "llm_decision":
                    self._current_step.llm_time += duration
                elif operation == "screenshot":
                    self._current_step.screenshot_time += duration
                    self._current_step.screenshot_count += 1
                elif operation == "action":
                    self._current_step.action_time += duration
                elif operation == "verify":
                    self._current_step.verify_time += duration
                elif operation == "stable_wait":
                    self._current_step.stable_wait_time += duration
    
    def get_summary(self) -> Dict[str, Any]:
        """Get profiling summary as dict."""
        if not self._step_profiles:
            return {"steps": [], "total_time": 0}
        
        total_time = time.perf_counter() - self._start_time if self._start_time else 0
        
        # Aggregate stats
        total_llm = sum(s.llm_time for s in self._step_profiles)
        total_screenshot = sum(s.screenshot_time for s in self._step_profiles)
        total_action = sum(s.action_time for s in self._step_profiles)
        total_verify = sum(s.verify_time for s in self._step_profiles)
        total_stable = sum(s.stable_wait_time for s in self._step_profiles)
        total_screenshots = sum(s.screenshot_count for s in self._step_profiles)
        
        return {
            "total_time": total_time,
            "step_count": len(self._step_profiles),
            "avg_step_time": total_time / len(self._step_profiles) if self._step_profiles else 0,
            "breakdown": {
                "llm_time": total_llm,
                "screenshot_time": total_screenshot,
                "action_time": total_action,
                "verify_time": total_verify,
                "stable_wait_time": total_stable,
            },
            "percentages": {
                "llm": (total_llm / total_time * 100) if total_time else 0,
                "screenshot": (total_screenshot / total_time * 100) if total_time else 0,
                "action": (total_action / total_time * 100) if total_time else 0,
                "verify": (total_verify / total_time * 100) if total_time else 0,
                "stable_wait": (total_stable / total_time * 100) if total_time else 0,
            },
            "screenshot_count": total_screenshots,
            "steps": [
                {
                    "step": s.step,
                    "total": s.total_time,
                    "llm": s.llm_time,
                    "screenshot": s.screenshot_time,
                    "action": s.action_time,
                    "verify": s.verify_time,
                    "stable_wait": s.stable_wait_time,
                }
                for s in self._step_profiles
            ],
        }
    
    def get_report(self) -> str:
        """Get formatted profiling report for console output."""
        summary = self.get_summary()
        
        if not summary["steps"]:
            return "No profiling data collected."
        
        lines = [
            "",
            "📊 Performance Profile",
            "─" * 70,
            f"Total Time: {summary['total_time']:.1f}s | Steps: {summary['step_count']} | Avg: {summary['avg_step_time']:.1f}s/step",
            "",
        ]
        
        # Breakdown table header
        lines.append(f"{'Step':>4} | {'LLM':>6} | {'Screen':>6} | {'Action':>6} | {'Verify':>6} | {'Stable':>6} | {'Total':>6}")
        lines.append("─" * 70)
        
        # Per-step breakdown
        for s in summary["steps"]:
            lines.append(
                f"{s['step']:>4} | {s['llm']:>5.1f}s | {s['screenshot']:>5.1f}s | "
                f"{s['action']:>5.1f}s | {s['verify']:>5.1f}s | {s['stable_wait']:>5.1f}s | {s['total']:>5.1f}s"
            )
        
        lines.append("─" * 70)
        
        # Totals
        b = summary["breakdown"]
        lines.append(
            f"{'Total':>4} | {b['llm_time']:>5.1f}s | {b['screenshot_time']:>5.1f}s | "
            f"{b['action_time']:>5.1f}s | {b['verify_time']:>5.1f}s | {b['stable_wait_time']:>5.1f}s | {summary['total_time']:>5.1f}s"
        )
        
        # Percentages
        lines.append("")
        p = summary["percentages"]
        lines.append(f"Bottlenecks: LLM {p['llm']:.0f}% | Verify {p['verify']:.0f}% | Stable {p['stable_wait']:.0f}%")
        lines.append(f"Screenshots captured: {summary['screenshot_count']}")
        
        return "\n".join(lines)
    
    def get_deep_profile_report(self) -> str:
        """Get cProfile report for deep profiling."""
        if not self._cprofile:
            return "Deep profiling not enabled."
        
        try:
            import io
            import pstats
            
            stream = io.StringIO()
            stats = pstats.Stats(self._cprofile, stream=stream)
            stats.sort_stats("cumulative")
            stats.print_stats(20)  # Top 20 functions
            
            return f"\n📊 Deep Profile (cProfile)\n{'─' * 70}\n{stream.getvalue()}"
        except Exception as e:
            return f"Deep profile error: {e}"
    
    def save_to_file(self, path: str):
        """Save profile data to JSON file."""
        import json
        
        summary = self.get_summary()
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Profile saved to {path}")


# Global profiler instance (created when --profile is used)
_profiler: Optional[StepProfiler] = None


def get_profiler() -> Optional[StepProfiler]:
    """Get global profiler instance."""
    return _profiler


def init_profiler(enabled: bool = True, deep_profile: bool = False) -> StepProfiler:
    """Initialize global profiler."""
    global _profiler
    _profiler = StepProfiler(enabled=enabled, deep_profile=deep_profile)
    _profiler.start()
    return _profiler


def stop_profiler() -> Optional[str]:
    """Stop profiler and return report."""
    global _profiler
    if _profiler:
        _profiler.stop()
        return _profiler.get_report()
    return None
