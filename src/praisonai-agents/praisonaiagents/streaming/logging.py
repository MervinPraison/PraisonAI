"""
Streaming logging utilities for PraisonAI.

Provides guarded logging for streaming events with clear timestamps
for request_start, headers_received, first_token, last_token, and stream_end.

Usage:
    from praisonaiagents.streaming.logging import StreamLogger
    
    logger = StreamLogger(verbose=True, metrics=True)
    logger.log_request_start(model="gpt-4o-mini")
    # ... streaming ...
    logger.log_first_token()
    # ... more tokens ...
    logger.log_stream_end()
    print(logger.get_metrics_summary())
"""

import logging
import time
from typing import Optional, Dict, Any

from .events import StreamMetrics, StreamEvent, StreamEventType


class StreamLogger:
    """
    Guarded logging for streaming events with timing metrics.
    
    Only logs when verbose=True or metrics=True to ensure zero overhead
    when logging is disabled.
    
    Attributes:
        verbose: Whether to log detailed streaming events
        metrics: Whether to collect and display timing metrics
    """
    
    def __init__(
        self,
        verbose: bool = False,
        metrics: bool = False,
        logger: Optional[logging.Logger] = None
    ):
        self.verbose = verbose
        self.metrics = metrics
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = StreamMetrics() if metrics else None
        self._enabled = verbose or metrics
    
    def log_request_start(
        self,
        model: Optional[str] = None,
        message_count: Optional[int] = None
    ) -> None:
        """Log when the streaming request is initiated."""
        if not self._enabled:
            return
        
        timestamp = time.perf_counter()
        if self._metrics:
            self._metrics.request_start = timestamp
        
        if self.verbose:
            extra = f" model={model}" if model else ""
            extra += f" messages={message_count}" if message_count else ""
            self._logger.info(f"[STREAM] REQUEST_START{extra}")
    
    def log_headers_received(self) -> None:
        """Log when HTTP response headers are received."""
        if not self._enabled:
            return
        
        timestamp = time.perf_counter()
        if self._metrics:
            self._metrics.headers_received = timestamp
        
        if self.verbose:
            self._logger.info("[STREAM] HEADERS_RECEIVED")
    
    def log_first_token(self, content: Optional[str] = None) -> None:
        """Log when the first content token is received (TTFT marker)."""
        if not self._enabled:
            return
        
        timestamp = time.perf_counter()
        if self._metrics:
            self._metrics.first_token = timestamp
            self._metrics.token_count = 1
        
        if self.verbose:
            preview = content[:20] + "..." if content and len(content) > 20 else content
            self._logger.info(f"[STREAM] FIRST_TOKEN content={preview!r}")
    
    def log_delta_text(self, content: Optional[str] = None) -> None:
        """Log a text delta (only when verbose, not for every token)."""
        if not self._enabled:
            return
        
        if self._metrics:
            self._metrics.token_count += 1
        
        # Don't log every delta to avoid noise - just track metrics
    
    def log_last_token(self) -> None:
        """Log when the last content token is received."""
        if not self._enabled:
            return
        
        timestamp = time.perf_counter()
        if self._metrics:
            self._metrics.last_token = timestamp
        
        if self.verbose:
            self._logger.info("[STREAM] LAST_TOKEN")
    
    def log_stream_end(self, chunk_count: Optional[int] = None) -> None:
        """Log when the stream ends."""
        if not self._enabled:
            return
        
        timestamp = time.perf_counter()
        if self._metrics:
            self._metrics.stream_end = timestamp
        
        if self.verbose:
            extra = f" chunks={chunk_count}" if chunk_count else ""
            self._logger.info(f"[STREAM] STREAM_END{extra}")
    
    def log_error(self, error: str) -> None:
        """Log a streaming error."""
        if self.verbose:
            self._logger.error(f"[STREAM] ERROR: {error}")
    
    def get_metrics(self) -> Optional[StreamMetrics]:
        """Get the collected metrics (None if metrics not enabled)."""
        return self._metrics
    
    def get_metrics_summary(self) -> str:
        """Get a formatted summary of streaming metrics."""
        if not self._metrics:
            return "Metrics not enabled"
        return self._metrics.format_summary()
    
    def get_metrics_dict(self) -> Optional[Dict[str, Any]]:
        """Get metrics as a dictionary."""
        if not self._metrics:
            return None
        return self._metrics.to_dict()
    
    def update_from_event(self, event: StreamEvent) -> None:
        """Update logger state from a StreamEvent."""
        if not self._enabled:
            return
        
        if self._metrics:
            self._metrics.update_from_event(event)
        
        if self.verbose:
            if event.type == StreamEventType.REQUEST_START:
                self.log_request_start()
            elif event.type == StreamEventType.HEADERS_RECEIVED:
                self.log_headers_received()
            elif event.type == StreamEventType.FIRST_TOKEN:
                self.log_first_token(event.content)
            elif event.type == StreamEventType.LAST_TOKEN:
                self.log_last_token()
            elif event.type == StreamEventType.STREAM_END:
                self.log_stream_end()
            elif event.type == StreamEventType.ERROR:
                self.log_error(event.error or "Unknown error")


def create_logging_callback(
    verbose: bool = False,
    metrics: bool = False,
    logger: Optional[logging.Logger] = None
) -> tuple:
    """
    Create a StreamLogger and a callback function for use with streaming.
    
    Args:
        verbose: Whether to log detailed events
        metrics: Whether to collect timing metrics
        logger: Optional custom logger
    
    Returns:
        Tuple of (StreamLogger, callback_function)
    
    Usage:
        stream_logger, callback = create_logging_callback(verbose=True, metrics=True)
        
        # Pass callback to streaming method
        response = client.process_stream_response(
            ...,
            stream_callback=callback,
            emit_events=True
        )
        
        # After streaming, get metrics
        print(stream_logger.get_metrics_summary())
    """
    stream_logger = StreamLogger(verbose=verbose, metrics=metrics, logger=logger)
    
    def callback(event: StreamEvent) -> None:
        stream_logger.update_from_event(event)
    
    return stream_logger, callback
