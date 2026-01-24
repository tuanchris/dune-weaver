# Testing Guide

This document explains how to run tests for the Dune Weaver backend.

## Quick Start

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all unit tests (no hardware needed)
pytest tests/unit/ -v

# Run with coverage report
pytest tests/ --cov=modules --cov-report=term-missing
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (run in CI, no hardware)
│   ├── conftest.py
│   ├── test_api_patterns.py
│   ├── test_api_playlists.py
│   ├── test_api_status.py
│   ├── test_connection_manager.py
│   ├── test_pattern_manager.py
│   └── test_playlist_manager.py
├── integration/             # Integration tests (require hardware)
│   ├── conftest.py
│   ├── test_hardware.py
│   ├── test_playback_controls.py
│   └── test_playlist.py
└── fixtures/                # Test data files
```

## Unit Tests

Unit tests mock all hardware dependencies and run quickly. They're safe to run anywhere.

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_pattern_manager.py -v

# Run specific test
pytest tests/unit/test_api_status.py::test_get_status -v

# Run tests matching a pattern
pytest tests/unit/ -v -k "playlist"
```

## Integration Tests

Integration tests require the sand table hardware to be connected. They are **skipped by default**.

```bash
# Run integration tests (with hardware connected)
pytest tests/integration/ --run-hardware -v

# Run specific integration test file
pytest tests/integration/test_playback_controls.py --run-hardware -v

# Run with output visible (helpful for debugging)
pytest tests/integration/ --run-hardware -v -s
```

### Integration Test Categories

| File | What it tests | Duration |
|------|---------------|----------|
| `test_hardware.py` | Serial connection, homing, movement, pattern execution | ~5-10 min |
| `test_playback_controls.py` | Pause, resume, stop, skip, speed control | ~5 min |
| `test_playlist.py` | Playlist modes, clear patterns, state updates | ~5 min |

### Safety Notes

- **Movement tests physically move the table** — ensure the ball path is clear
- **Homing tests run the homing sequence** — table will move to home position
- **Pattern tests execute real patterns** — star.thr runs end-to-end

## Coverage Reports

```bash
# Terminal report
pytest tests/ --cov=modules --cov-report=term-missing

# HTML report (creates htmlcov/ directory)
pytest tests/ --cov=modules --cov-report=html
open htmlcov/index.html

# XML report (for CI tools)
pytest tests/ --cov=modules --cov-report=xml
```

## CI Behavior

When `CI=true` environment variable is set:
- All `@pytest.mark.hardware` tests are automatically skipped
- Unit tests run normally

```bash
# Simulate CI environment locally
CI=true pytest tests/ -v
```

## Common Commands

| Command | Description |
|---------|-------------|
| `pytest tests/unit/ -v` | Run unit tests |
| `pytest tests/integration/ --run-hardware -v` | Run integration tests |
| `pytest tests/ --cov=modules` | Run with coverage |
| `pytest tests/ -v -k "pattern"` | Run tests matching "pattern" |
| `pytest tests/ -x` | Stop on first failure |
| `pytest tests/ --lf` | Run only last failed tests |
| `pytest tests/ -v -s` | Show print statements |

## Adding New Tests

### Unit Test Example

```python
# tests/unit/test_my_feature.py
import pytest
from unittest.mock import MagicMock, patch

def test_my_function():
    """Test description here."""
    # Arrange
    expected = "result"

    # Act
    result = my_function()

    # Assert
    assert result == expected

@pytest.mark.asyncio
async def test_async_function(async_client):
    """Test async endpoint."""
    response = await async_client.get("/my_endpoint")
    assert response.status_code == 200
```

### Integration Test Example

```python
# tests/integration/test_my_hardware.py
import pytest

@pytest.mark.hardware
@pytest.mark.slow
def test_hardware_operation(hardware_port, run_hardware):
    """Test that requires real hardware."""
    if not run_hardware:
        pytest.skip("Hardware tests disabled")

    from modules.connection import connection_manager

    conn = connection_manager.SerialConnection(hardware_port)
    try:
        assert conn.is_connected()
        # ... test hardware operation
    finally:
        conn.close()
```

## Troubleshooting

### Tests hang or timeout
- Check if hardware is connected and powered on
- Verify serial port is not in use by another application
- Try running with `-s` flag to see output

### Import errors
- Ensure you're in the project root directory
- Install dependencies: `pip install -r requirements-dev.txt`

### Hardware tests skip unexpectedly
- Make sure to pass `--run-hardware` flag
- Check that `CI` environment variable is not set

### Coverage shows 0%
- Ensure `relative_files = true` is in pyproject.toml
- Run from project root directory
