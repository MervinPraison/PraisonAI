"""Health monitoring and telemetry for circuit breakers.

Provides health monitoring, telemetry collection, and observability
for circuit breaker patterns in PraisonAI.

Following the protocol-driven architecture from AGENTS.md.
"""

import asyncio
import json
import logging
from praisonaiagents._logging import get_logger
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable, Union
from datetime import datetime, timedelta

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerStats, get_all_circuit_breaker_stats

logger = get_logger(__name__)

@dataclass
class HealthMetrics:
    """Health metrics for a service."""
    service_name: str
    is_healthy: bool
    response_time_ms: Optional[float] = None
    error_rate: float = 0.0
    last_check_time: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_checks: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for telemetry."""
        return {
            "service_name": self.service_name,
            "is_healthy": self.is_healthy,
            "response_time_ms": self.response_time_ms,
            "error_rate": self.error_rate,
            "last_check_time": self.last_check_time,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "total_checks": self.total_checks,
        }

@dataclass
class ServiceHealthConfig:
    """Configuration for service health monitoring."""
    check_interval: float = 30.0  # seconds
    timeout: float = 10.0  # seconds
    healthy_threshold: int = 2  # consecutive successes to be healthy
    unhealthy_threshold: int = 3  # consecutive failures to be unhealthy
    enable_metrics: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_interval": self.check_interval,
            "timeout": self.timeout,
            "healthy_threshold": self.healthy_threshold,
            "unhealthy_threshold": self.unhealthy_threshold,
            "enable_metrics": self.enable_metrics,
        }

@runtime_checkable
class HealthCheckProtocol(Protocol):
    """Protocol for health check implementations."""
    
    def check_health(self) -> bool:
        """Perform synchronous health check."""
        ...
    
    async def acheck_health(self) -> bool:
        """Perform asynchronous health check."""
        ...

@runtime_checkable
class TelemetryProtocol(Protocol):
    """Protocol for telemetry implementations."""
    
    def emit_health_metric(self, metrics: HealthMetrics) -> None:
        """Emit health metrics."""
        ...
    
    def emit_circuit_breaker_event(self, service_name: str, event_type: str, data: Dict[str, Any]) -> None:
        """Emit circuit breaker events."""
        ...

class HealthMonitor:
    """Health monitor for external services with circuit breaker integration.
    
    Monitors service health and integrates with circuit breakers for
    proactive failure detection and recovery.
    
    Example:
        monitor = HealthMonitor()
        
        # Add service with health check
        def db_health_check():
            return ping_database()
        
        monitor.add_service("database", db_health_check)
        monitor.start()
        
        # Check health status
        health = monitor.get_health("database")
        print(f"Database healthy: {health.is_healthy}")
    """
    
    def __init__(self, telemetry: Optional[TelemetryProtocol] = None):
        """Initialize health monitor.
        
        Args:
            telemetry: Optional telemetry provider
        """
        self._telemetry = telemetry
        self._services: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, HealthMetrics] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()
        
        # Event callbacks
        self._on_health_change_callbacks: List[Callable[[str, bool], None]] = []
    
    def add_service(
        self,
        name: str,
        health_check: Union[Callable[[], bool], HealthCheckProtocol],
        config: Optional[ServiceHealthConfig] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """Add a service to monitor.
        
        Args:
            name: Service name
            health_check: Health check function or protocol
            config: Health monitoring configuration
            circuit_breaker: Associated circuit breaker
        """
        with self._lock:
            self._services[name] = {
                "health_check": health_check,
                "config": config or ServiceHealthConfig(),
                "circuit_breaker": circuit_breaker,
                "last_check": 0.0,
            }
            
            # Initialize metrics
            self._metrics[name] = HealthMetrics(
                service_name=name,
                is_healthy=True,  # Assume healthy initially
            )
    
    def remove_service(self, name: str) -> bool:
        """Remove a service from monitoring.
        
        Args:
            name: Service name
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            removed = name in self._services
            self._services.pop(name, None)
            self._metrics.pop(name, None)
            return removed
    
    def get_health(self, name: str) -> Optional[HealthMetrics]:
        """Get health metrics for a service.
        
        Args:
            name: Service name
            
        Returns:
            Health metrics or None if service not found
        """
        with self._lock:
            return self._metrics.get(name)
    
    def get_all_health(self) -> Dict[str, HealthMetrics]:
        """Get health metrics for all services."""
        with self._lock:
            return dict(self._metrics)
    
    def start(self) -> None:
        """Start health monitoring."""
        if self._running:
            return
        
        self._running = True
        
        # Start monitoring task if we have an event loop
        try:
            loop = asyncio.get_event_loop()
            self._monitor_task = loop.create_task(self._monitor_loop())
            logger.info("Health monitor started")
        except RuntimeError:
            # No event loop running, start in background thread
            threading.Thread(target=self._monitor_in_thread, daemon=True).start()
            logger.info("Health monitor started in background thread")
    
    def stop(self) -> None:
        """Stop health monitoring."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        
        logger.info("Health monitor stopped")
    
    def on_health_change(self, callback: Callable[[str, bool], None]) -> None:
        """Register callback for health status changes.
        
        Args:
            callback: Function called with (service_name, is_healthy)
        """
        self._on_health_change_callbacks.append(callback)
    
    async def check_service_health(self, name: str) -> Optional[bool]:
        """Manually check health for a specific service.
        
        Args:
            name: Service name
            
        Returns:
            True if healthy, False if unhealthy, None if service not found
        """
        with self._lock:
            if name not in self._services:
                return None
            
            service_info = self._services[name]
            health_check = service_info["health_check"]
            config = service_info["config"]
        
        # Perform health check with timeout
        start_time = time.time()
        is_healthy = False
        
        try:
            if hasattr(health_check, 'acheck_health'):
                # Protocol with async method
                is_healthy = await asyncio.wait_for(
                    health_check.acheck_health(),
                    timeout=config.timeout
                )
            elif asyncio.iscoroutinefunction(health_check):
                # Async function
                is_healthy = await asyncio.wait_for(
                    health_check(),
                    timeout=config.timeout
                )
            else:
                # Sync function - run in executor
                loop = asyncio.get_event_loop()
                is_healthy = await loop.run_in_executor(
                    None,
                    lambda: health_check() if callable(health_check) else health_check.check_health()
                )
        except Exception as e:
            logger.warning(f"Health check failed for {name}: {e}")
            is_healthy = False
        
        response_time = (time.time() - start_time) * 1000  # ms
        
        # Update metrics
        with self._lock:
            metrics = self._metrics.get(name)
            if metrics:
                previous_health = metrics.is_healthy
                
                if is_healthy:
                    metrics.consecutive_successes += 1
                    metrics.consecutive_failures = 0
                    
                    # Consider healthy after threshold successes
                    if metrics.consecutive_successes >= config.healthy_threshold:
                        metrics.is_healthy = True
                else:
                    metrics.consecutive_failures += 1
                    metrics.consecutive_successes = 0
                    
                    # Consider unhealthy after threshold failures
                    if metrics.consecutive_failures >= config.unhealthy_threshold:
                        metrics.is_healthy = False
                
                metrics.response_time_ms = response_time
                metrics.last_check_time = time.time()
                metrics.total_checks += 1
                
                # Calculate error rate (last 100 checks)
                # Simplified implementation
                if metrics.total_checks > 0:
                    metrics.error_rate = metrics.consecutive_failures / min(metrics.total_checks, 100)
                
                # Emit telemetry
                if config.enable_metrics and self._telemetry:
                    self._telemetry.emit_health_metric(metrics)
                
                # Notify health status changes
                if metrics.is_healthy != previous_health:
                    for callback in self._on_health_change_callbacks:
                        try:
                            callback(name, metrics.is_healthy)
                        except Exception as e:
                            logger.error(f"Health change callback error: {e}")
                    
                    # Emit circuit breaker event
                    if self._telemetry:
                        self._telemetry.emit_circuit_breaker_event(
                            name,
                            "health_change",
                            {
                                "is_healthy": metrics.is_healthy,
                                "response_time_ms": response_time,
                                "consecutive_failures": metrics.consecutive_failures,
                                "consecutive_successes": metrics.consecutive_successes,
                            }
                        )
                
                # Update associated circuit breaker
                circuit_breaker = service_info.get("circuit_breaker")
                if circuit_breaker:
                    if metrics.is_healthy and circuit_breaker.state == CircuitState.OPEN:
                        # Service recovered, reset circuit breaker
                        circuit_breaker.reset()
                        logger.info(f"Circuit breaker reset for {name} - service recovered")
        
        return is_healthy
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                # Check all services
                for name in list(self._services.keys()):
                    if not self._running:
                        break
                    
                    with self._lock:
                        if name not in self._services:
                            continue
                        
                        service_info = self._services[name]
                        config = service_info["config"]
                        last_check = service_info["last_check"]
                    
                    # Check if it's time for health check
                    current_time = time.time()
                    if current_time - last_check >= config.check_interval:
                        await self.check_service_health(name)
                        
                        with self._lock:
                            if name in self._services:
                                self._services[name]["last_check"] = current_time
                
                # Sleep for a short interval before next iteration
                await asyncio.sleep(1.0)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(5.0)  # Wait before retrying
    
    def _monitor_in_thread(self) -> None:
        """Run monitoring loop in a background thread."""
        asyncio.run(self._monitor_loop())

class ConsoleTelemetry:
    """Simple console-based telemetry implementation."""
    
    def emit_health_metric(self, metrics: HealthMetrics) -> None:
        """Emit health metrics to console."""
        logger.info(f"Health metric: {metrics.service_name} - "
                   f"healthy={metrics.is_healthy}, "
                   f"response_time={metrics.response_time_ms}ms")
    
    def emit_circuit_breaker_event(self, service_name: str, event_type: str, data: Dict[str, Any]) -> None:
        """Emit circuit breaker events to console."""
        logger.info(f"Circuit breaker event: {service_name} - {event_type} - {data}")

class JsonFileTelemetry:
    """JSON file-based telemetry implementation."""
    
    def __init__(self, file_path: str):
        """Initialize with file path for telemetry data.
        
        Args:
            file_path: Path to JSON file for telemetry data
        """
        self.file_path = file_path
        self._lock = threading.Lock()
    
    def emit_health_metric(self, metrics: HealthMetrics) -> None:
        """Emit health metrics to JSON file."""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "health_metric",
            "data": metrics.to_dict()
        }
        self._append_to_file(data)
    
    def emit_circuit_breaker_event(self, service_name: str, event_type: str, data: Dict[str, Any]) -> None:
        """Emit circuit breaker events to JSON file."""
        event_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "circuit_breaker_event",
            "service_name": service_name,
            "event_type": event_type,
            "data": data
        }
        self._append_to_file(event_data)
    
    def _append_to_file(self, data: Dict[str, Any]) -> None:
        """Thread-safely append data to JSON file."""
        with self._lock:
            try:
                with open(self.file_path, 'a') as f:
                    f.write(json.dumps(data) + '\n')
            except Exception as e:
                logger.error(f"Failed to write telemetry to {self.file_path}: {e}")

def get_circuit_breaker_dashboard_data() -> Dict[str, Any]:
    """Get comprehensive dashboard data for circuit breakers and health monitoring.
    
    Returns:
        Dashboard data including circuit breaker stats and health metrics
    """
    from .circuit_breaker import _global_registry
    
    # Get all circuit breaker stats
    cb_stats = get_all_circuit_breaker_stats()
    
    # Get health monitor instance if available
    health_data = {}
    # This would need to be managed globally or passed in
    
    # Aggregate data
    dashboard_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "circuit_breakers": cb_stats,
        "health_monitors": health_data,
        "summary": {
            "total_services": len(cb_stats),
            "open_circuits": sum(1 for stats in cb_stats.values() if stats.get("state") == "open"),
            "unhealthy_services": sum(1 for stats in cb_stats.values() if stats.get("state") != "closed"),
        }
    }
    
    return dashboard_data

# Global health monitor instance for convenience (lazy initialization)
_global_health_monitor = None
_global_health_monitor_lock = threading.Lock()

def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _global_health_monitor
    with _global_health_monitor_lock:
        if _global_health_monitor is None:
            _global_health_monitor = HealthMonitor()
        return _global_health_monitor