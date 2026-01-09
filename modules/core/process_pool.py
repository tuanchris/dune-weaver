"""Shared process pool for CPU-intensive tasks.

Provides a single ProcessPoolExecutor shared across modules to:
- Isolate CPU-intensive work from the motion control thread (separate GILs)
- Manage worker count based on available CPUs
- Configure CPU affinity to keep workers off CPU 0 (reserved for motion)
"""
import logging
from concurrent.futures import ProcessPoolExecutor
from modules.core import scheduling

logger = logging.getLogger(__name__)

_pool: ProcessPoolExecutor | None = None


def _get_worker_count() -> int:
    """Calculate optimal worker count.
    
    - Reserve 1 CPU for motion control thread
    - Max 3 workers (diminishing returns beyond)
    - Min 1 worker
    """
    return min(3, max(1, scheduling.get_cpu_count() - 1))


def setup_worker_process():
    """Configure worker process (called at worker startup).
    
    Sets CPU affinity and lowers priority.
    """
    scheduling.setup_background_worker()


def init_pool() -> ProcessPoolExecutor:
    """Initialize the shared process pool."""
    global _pool
    if _pool is not None:
        return _pool
    
    worker_count = _get_worker_count()
    cpu_count = scheduling.get_cpu_count()
    _pool = ProcessPoolExecutor(max_workers=worker_count)
    logger.info(f"Process pool initialized: {worker_count} workers, {cpu_count} CPUs")
    return _pool


def get_pool() -> ProcessPoolExecutor:
    """Get the shared process pool (must be initialized first)."""
    if _pool is None:
        raise RuntimeError("Process pool not initialized - call init_pool() first")
    return _pool


def shutdown_pool(wait: bool = True, cancel_futures: bool = False):
    """Shutdown the process pool."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=wait, cancel_futures=cancel_futures)
        _pool = None
        logger.info("Process pool shut down")

