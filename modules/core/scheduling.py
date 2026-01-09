"""Scheduling utilities for thread/process priority and CPU affinity.

Provides centralized functions to configure scheduling for:
- Real-time I/O threads (motion control, LED effects) - high priority, CPU 0
- Background workers (preview generation, file parsing) - low priority, CPUs 1-N
"""
import os
import sys
import ctypes
import ctypes.util
import logging

logger = logging.getLogger(__name__)


def get_cpu_count() -> int:
    """Get available CPU cores."""
    return os.cpu_count() or 1


def get_background_cpus() -> set[int] | None:
    """Get CPU set for background work (all except CPU 0).
    
    Returns None on single-core systems.
    """
    cpu_count = get_cpu_count()
    if cpu_count <= 1:
        return None
    return set(range(1, cpu_count))


def elevate_priority(tid: int | None = None, realtime_priority: int = 50) -> bool:
    """Elevate thread/process to real-time priority.
    
    Attempts SCHED_RR (real-time round-robin) first, falls back to nice -10.
    Requires CAP_SYS_NICE capability for full real-time scheduling.
    
    Args:
        tid: Thread/process ID. If None, uses current thread (0).
        realtime_priority: SCHED_RR priority (1-99, default 50).
    
    Returns:
        True if any elevation succeeded.
    """
    if sys.platform != 'linux':
        logger.debug("Priority elevation only supported on Linux")
        return False
    
    target_id = tid if tid is not None else 0
    
    # Try SCHED_RR (real-time round-robin)
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
        
        SCHED_RR = 2
        
        class sched_param(ctypes.Structure):
            _fields_ = [('sched_priority', ctypes.c_int)]
        
        param = sched_param(realtime_priority)
        result = libc.sched_setscheduler(target_id, SCHED_RR, ctypes.byref(param))
        
        if result == 0:
            logger.info(f"Thread {target_id} set to SCHED_RR priority {realtime_priority}")
            return True
        else:
            errno = ctypes.get_errno()
            logger.debug(f"SCHED_RR failed with errno {errno}, trying nice fallback")
    except Exception as e:
        logger.debug(f"SCHED_RR setup failed: {e}, trying nice fallback")
    
    # Fallback: negative nice value
    try:
        current_nice = os.nice(0)
        if current_nice > -10:
            os.nice(-10 - current_nice)
            logger.info("Process priority elevated via nice(-10)")
            return True
    except PermissionError:
        logger.info("Priority elevation requires CAP_SYS_NICE capability - using default priority")
    except Exception as e:
        logger.debug(f"Nice priority elevation failed: {e}")
    
    return False


def lower_priority(nice_value: int = 10) -> bool:
    """Lower current thread/process priority for background work.
    
    Args:
        nice_value: Nice value to set (positive = lower priority).
    
    Returns:
        True if priority was lowered.
    """
    if sys.platform != 'linux':
        return False
    
    try:
        os.nice(nice_value)
        logger.debug(f"Process priority lowered via nice(+{nice_value})")
        return True
    except Exception as e:
        logger.debug(f"Could not lower priority: {e}")
        return False


def pin_to_cpu(cpu_id: int, tid: int | None = None) -> bool:
    """Pin thread/process to a specific CPU core.
    
    Args:
        cpu_id: CPU core number (0-indexed).
        tid: Thread/process ID. If None, uses current (0).
    
    Returns:
        True if affinity was set.
    """
    return pin_to_cpus({cpu_id}, tid)


def pin_to_cpus(cpu_ids: set[int], tid: int | None = None) -> bool:
    """Pin thread/process to multiple CPU cores.
    
    Args:
        cpu_ids: Set of CPU core numbers.
        tid: Thread/process ID. If None, uses current (0).
    
    Returns:
        True if affinity was set.
    """
    if sys.platform != 'linux':
        return False
    
    if not cpu_ids:
        return False
    
    target_id = tid if tid is not None else 0
    
    try:
        os.sched_setaffinity(target_id, cpu_ids)
        cpu_str = ','.join(map(str, sorted(cpu_ids)))
        logger.debug(f"Thread {target_id} pinned to CPU(s) {cpu_str}")
        return True
    except Exception as e:
        logger.debug(f"CPU affinity not set: {e}")
        return False


def setup_realtime_thread(tid: int | None = None) -> None:
    """Setup for time-critical I/O threads (motion control, LED effects).
    
    Elevates priority and pins to CPU 0.
    
    Args:
        tid: Thread native_id. If None, uses current thread.
    """
    cpu_count = get_cpu_count()
    
    # Elevate priority
    elevated = elevate_priority(tid)
    
    # Pin to CPU 0 if multi-core
    if cpu_count > 1:
        pinned = pin_to_cpu(0, tid)
        if pinned:
            logger.info(f"Real-time thread pinned to CPU 0 ({cpu_count} CPUs detected)")
    
    if elevated:
        logger.info("Real-time thread priority elevated")


def setup_background_worker() -> None:
    """Setup for CPU-intensive background workers.
    
    Lowers priority and pins to CPUs 1-N (avoiding CPU 0).
    Called at worker process startup.
    """
    # Lower priority
    lower_priority(10)
    
    # Pin to background CPUs (1-N)
    worker_cpus = get_background_cpus()
    if worker_cpus:
        pin_to_cpus(worker_cpus)
        cpu_str = ','.join(map(str, sorted(worker_cpus)))
        logger.debug(f"Background worker pinned to CPUs {cpu_str}")
