"""
Memory-based log handler for capturing and streaming application logs.

This module provides a circular buffer log handler that captures log messages
in memory for display in the web UI, with support for real-time streaming
via WebSocket.
"""

import logging
from collections import deque
from datetime import datetime
from typing import List, Dict, Any
import threading
import asyncio


class MemoryLogHandler(logging.Handler):
    """
    A logging handler that stores log records in a circular buffer.

    Thread-safe implementation using a lock for concurrent access.
    Supports async iteration for WebSocket streaming.
    """

    def __init__(self, max_entries: int = 500):
        """
        Initialize the memory log handler.

        Args:
            max_entries: Maximum number of log entries to keep in memory.
                        Older entries are automatically discarded.
        """
        super().__init__()
        self.max_entries = max_entries
        self._buffer: deque = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._subscribers: List[asyncio.Queue] = []
        self._subscribers_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Store a log record in the buffer and notify subscribers.

        Args:
            record: The log record to store.
        """
        try:
            log_entry = self._format_record(record)

            with self._lock:
                self._buffer.append(log_entry)

            # Notify all subscribers (for WebSocket streaming)
            self._notify_subscribers(log_entry)

        except Exception:
            self.handleError(record)

    def _format_record(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Format a log record into a dictionary for JSON serialization.

        Args:
            record: The log record to format.

        Returns:
            Dictionary containing formatted log data.
        """
        return {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "line": record.lineno,
            "message": record.getMessage(),
            "module": record.module,
        }

    def get_logs(self, limit: int = None, level: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve stored log entries.

        Args:
            limit: Maximum number of entries to return (newest first).
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

        Returns:
            List of log entries as dictionaries.
        """
        with self._lock:
            logs = list(self._buffer)

        # Filter by level if specified
        if level:
            level_upper = level.upper()
            logs = [log for log in logs if log["level"] == level_upper]

        # Return newest first, with optional limit
        logs.reverse()
        if limit:
            logs = logs[:limit]

        return logs

    def clear(self) -> None:
        """Clear all stored log entries."""
        with self._lock:
            self._buffer.clear()

    def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to real-time log updates.

        Returns:
            An asyncio Queue that will receive new log entries.
        """
        queue = asyncio.Queue(maxsize=100)
        with self._subscribers_lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Unsubscribe from real-time log updates.

        Args:
            queue: The queue returned by subscribe().
        """
        with self._subscribers_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _notify_subscribers(self, log_entry: Dict[str, Any]) -> None:
        """
        Notify all subscribers of a new log entry.

        Args:
            log_entry: The formatted log entry to send.
        """
        with self._subscribers_lock:
            dead_subscribers = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    # If queue is full, skip this entry
                    pass
                except Exception:
                    dead_subscribers.append(queue)

            # Remove dead subscribers
            for queue in dead_subscribers:
                self._subscribers.remove(queue)


# Global instance of the memory log handler
memory_handler: MemoryLogHandler = None


def init_memory_handler(max_entries: int = 500) -> MemoryLogHandler:
    """
    Initialize and install the memory log handler.

    This should be called once during application startup, after
    basicConfig but before any logging occurs.

    Args:
        max_entries: Maximum number of log entries to store.

    Returns:
        The initialized MemoryLogHandler instance.
    """
    global memory_handler

    memory_handler = MemoryLogHandler(max_entries=max_entries)
    memory_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s')
    )

    # Add to root logger to capture all logs
    root_logger = logging.getLogger()
    root_logger.addHandler(memory_handler)

    return memory_handler


def get_memory_handler() -> MemoryLogHandler:
    """
    Get the global memory log handler instance.

    Returns:
        The MemoryLogHandler instance, or None if not initialized.
    """
    return memory_handler
