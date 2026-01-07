"""Shared process pool for CPU-intensive tasks.

Provides a single ProcessPoolExecutor shared across modules to:
- Isolate CPU-intensive work from the motion control thread (separate GILs)
- Manage worker count based on available CPUs
- Configure CPU affinity to keep workers off CPU 0 (reserved for motion)
"""
import os
import sys
import logging
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger(__name__)

_pool: ProcessPoolExecutor | None = None


def _get_cpu_count() -> int:
    """Get available CPU cores."""
    return os.cpu_count() or 1


def _get_worker_count() -> int:
    """Calculate optimal worker count.
    
    - Reserve 1 CPU for motion control thread
    - Max 3 workers (diminishing returns beyond)
    - Min 1 worker
    """
    return min(3, max(1, _get_cpu_count() - 1))


def get_worker_cpu_affinity() -> set[int] | None:
    """Get CPU set for worker processes (excludes CPU 0).
    
    Returns None on single-core systems.
    """
    cpu_count = _get_cpu_count()
    if cpu_count <= 1:
        return None
    return set(range(1, cpu_count))


def setup_worker_process():
    """Configure worker process (called at worker startup).
    
    Sets CPU affinity and lowers priority.
    """
    if sys.platform != 'linux':
        return
    
    worker_cpus = get_worker_cpu_affinity()
    if worker_cpus:
        try:
            os.sched_setaffinity(0, worker_cpus)
        except Exception:
            pass
    
    try:
        os.nice(10)  # Lower priority
    except Exception:
        pass


def init_pool() -> ProcessPoolExecutor:
    """Initialize the shared process pool."""
    global _pool
    if _pool is not None:
        return _pool
    
    worker_count = _get_worker_count()
    cpu_count = _get_cpu_count()
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

