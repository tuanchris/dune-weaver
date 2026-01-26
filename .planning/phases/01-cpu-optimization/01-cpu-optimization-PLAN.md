# Phase 1: CPU Optimization — Execution Plan

```yaml
---
phase: 01-cpu-optimization
plan: 01
name: cpu-optimization
wave: 1
autonomous: true
scope: small
estimated_tasks: 6
requirements: REQ-LOG-01, REQ-LOG-02, REQ-LOG-03, REQ-LOG-04, REQ-LOG-05, REQ-LOG-06, REQ-TIMER-01, REQ-TIMER-02, REQ-WS-01, REQ-WS-02, REQ-CACHE-01, REQ-CACHE-02
must_haves:
  truths:
    - No console.log in main.qml MouseArea handlers (onPressed, onPositionChanged, onClicked)
    - No debug console.log in ConnectionStatus.qml
    - No debug console.log in ExecutionPage.qml
    - Screen timeout uses event-driven scheduling (no 1-second continuous timer)
    - WebSocket handler only emits signals when values change
    - Pattern preview paths are cached in a dictionary
  artifacts:
    - dune-weaver-touch/qml/main.qml (modified)
    - dune-weaver-touch/qml/components/ConnectionStatus.qml (modified)
    - dune-weaver-touch/qml/pages/ExecutionPage.qml (modified)
    - dune-weaver-touch/backend.py (modified)
---
```

## Objective

Eliminate CPU hotspots in the dune-weaver-touch Qt6 application to reduce idle CPU usage from 100%+ to under 20%.

## Context

### Files to Modify

| File | Changes | Requirements |
|------|---------|--------------|
| `dune-weaver-touch/qml/main.qml` | Remove console.log from MouseArea handlers + navigation logs | REQ-LOG-01, REQ-LOG-02, REQ-LOG-03 |
| `dune-weaver-touch/qml/components/ConnectionStatus.qml` | Remove all debug console.log | REQ-LOG-04 |
| `dune-weaver-touch/qml/pages/ExecutionPage.qml` | Remove debug console.log (keep functional code) | REQ-LOG-05 |
| `dune-weaver-touch/qml/pages/TableControlPage.qml` | Remove debug console.log | REQ-LOG-06 |
| `dune-weaver-touch/qml/pages/ModernPlaylistPage.qml` | Remove debug console.log | REQ-LOG-06 |
| `dune-weaver-touch/qml/components/ThemeManager.qml` | Remove debug console.log | REQ-LOG-06 |
| `dune-weaver-touch/qml/components/BottomNavTab.qml` | Remove debug console.log | REQ-LOG-06 |
| `dune-weaver-touch/backend.py` | Timer optimization, WebSocket optimization, preview cache | REQ-TIMER-01, REQ-TIMER-02, REQ-WS-01, REQ-WS-02, REQ-CACHE-01, REQ-CACHE-02 |

### Key Decisions (from STATE.md)

- Remove debug logs completely (not conditional flag)
- Event-driven screen timeout (not polling)

---

## Tasks

### Task 1: Remove console.log from main.qml MouseArea handlers

**Goal:** Eliminate the highest-impact CPU issue - logging on every pixel of touch movement.

**Files:** `dune-weaver-touch/qml/main.qml`

**Changes:**
1. Lines 97-110: Remove console.log from onPressed, onPositionChanged, onClicked
   - Keep `backend.resetActivityTimer()` calls
   - Delete only the console.log statements

**Before:**
```qml
onPressed: {
    console.log("🖥️ QML: Touch/press detected - resetting activity timer")
    backend.resetActivityTimer()
}

onPositionChanged: {
    console.log("🖥️ QML: Mouse movement detected - resetting activity timer")
    backend.resetActivityTimer()
}

onClicked: {
    console.log("🖥️ QML: Click detected - resetting activity timer")
    backend.resetActivityTimer()
}
```

**After:**
```qml
onPressed: {
    backend.resetActivityTimer()
}

onPositionChanged: {
    backend.resetActivityTimer()
}

onClicked: {
    backend.resetActivityTimer()
}
```

**Commit:** `perf(01-01): remove MouseArea console.log spam in main.qml`

---

### Task 2: Remove other debug console.log from main.qml

**Goal:** Remove remaining debug logs from main.qml.

**Files:** `dune-weaver-touch/qml/main.qml`

**Changes:** Remove console.log from:
- Line 28: `onCurrentPageIndexChanged`
- Lines 33-34, 38, 43: `onShouldNavigateToExecutionChanged`
- Lines 53-54, 60: `onExecutionStarted`
- Line 75: `onScreenStateChanged`
- Lines 79, 81, 84: `onBackendConnectionChanged`
- Line 137: `onRetryConnection`
- Line 157: `Component.onCompleted` in StackLayout
- Line 217: `onTabClicked`

**Commit:** `perf(01-01): remove remaining debug logs from main.qml`

---

### Task 3: Remove debug console.log from ConnectionStatus.qml

**Goal:** Eliminate logs that fire on every property access.

**Files:** `dune-weaver-touch/qml/components/ConnectionStatus.qml`

**Changes:** Remove all console.log statements (lines 15, 20, 34, 41, 43, 48, 50).

The color binding should be simplified to:
```qml
color: {
    if (!backend) return "#FF5722"
    return backend.serialConnected ? "#4CAF50" : "#FF5722"
}
```

Remove `onSerialConnectionChanged`, `Component.onCompleted`, and `onBackendChanged` debug handlers entirely (the color binding auto-updates).

**Commit:** `perf(01-01): remove debug logs from ConnectionStatus.qml`

---

### Task 4: Remove debug console.log from ExecutionPage.qml

**Goal:** Remove verbose debug logging from execution page.

**Files:** `dune-weaver-touch/qml/pages/ExecutionPage.qml`

**Changes:** Remove console.log from:
- Lines 17-21: `onBackendChanged`
- Lines 25-28: `Component.onCompleted`
- Lines 36, 40-42: `onSerialConnectionChanged`, `onConnectionChanged`
- Lines 47-49: `onExecutionStarted` (keep the property assignments)
- Lines 128, 130: Image source binding
- Lines 138-145: `onStatusChanged`
- Line 149: `onSourceChanged`

Keep the functional code, only remove logging.

**Commit:** `perf(01-01): remove debug logs from ExecutionPage.qml`

---

### Task 5: Remove debug console.log from other QML files

**Goal:** Clean up remaining QML files.

**Files:**
- `dune-weaver-touch/qml/pages/TableControlPage.qml` (lines 21, 26, 31, 39)
- `dune-weaver-touch/qml/pages/ModernPlaylistPage.qml` (lines 35, 43-44, 461, 470, 472, 475, 501, 564, 583, 1009, 1028, 1047, 1066)
- `dune-weaver-touch/qml/components/ThemeManager.qml` (line 70)
- `dune-weaver-touch/qml/components/BottomNavTab.qml` (lines 35, 45)

**Commit:** `perf(01-01): remove debug logs from remaining QML files`

---

### Task 6: Optimize backend.py - Timer, WebSocket, and Cache

**Goal:** Fix the three backend CPU issues.

**Files:** `dune-weaver-touch/backend.py`

**Changes:**

#### 6a: Event-driven screen timeout (REQ-TIMER-01, REQ-TIMER-02)

Replace continuous 1-second polling with event-driven scheduling.

**Current (lines 140-142):**
```python
self._screen_timer = QTimer()
self._screen_timer.timeout.connect(self._check_screen_timeout)
self._screen_timer.start(1000)  # Check every second
```

**New approach:**
```python
self._screen_timer = QTimer()
self._screen_timer.timeout.connect(self._screen_timeout_triggered)
self._screen_timer.setSingleShot(True)  # Only fires once
# Timer started in _reset_activity_timer() when activity detected
```

Update `_reset_activity_timer()` to:
1. Stop any existing timer
2. If screen timeout > 0, start a new single-shot timer for the timeout duration

Update `_check_screen_timeout()` → rename to `_screen_timeout_triggered()`:
- Simply turn off the screen (no time checking needed, timer already waited)

#### 6b: WebSocket signal optimization (REQ-WS-01, REQ-WS-02)

In `_on_ws_message()` (lines 310-364):
- Remove print statements (keep only error logging)
- Already checks for changes before emitting most signals - verify and keep this pattern

Remove prints from:
- Line 319: Pattern change logging
- Line 322: Preview path logging
- Line 332: Pause state logging
- Line 339: Serial connection logging
- Line 354: Speed change logging

#### 6c: Preview path caching (REQ-CACHE-01, REQ-CACHE-02)

Add a cache dictionary in `__init__`:
```python
self._preview_cache = {}  # filename -> preview_path
```

Modify `_find_pattern_preview()`:
```python
def _find_pattern_preview(self, fileName):
    # Check cache first
    if fileName in self._preview_cache:
        return self._preview_cache[fileName]

    # ... existing lookup logic ...

    # Cache the result (only positive results)
    if preview_path:
        self._preview_cache[fileName] = preview_path

    return preview_path
```

Add cache invalidation - add a method and call it when patterns might change:
```python
def _clear_preview_cache(self):
    self._preview_cache = {}
```

**Commit:** `perf(01-01): optimize timer, WebSocket, and preview cache in backend.py`

---

## Verification

After all tasks complete:

1. **Code verification:**
   - `grep -r "console.log" dune-weaver-touch/qml/` should return minimal results (only intentional user-facing logs if any)
   - `grep "_screen_timer.start(1000)" dune-weaver-touch/backend.py` should return nothing
   - `grep "_preview_cache" dune-weaver-touch/backend.py` should find cache usage

2. **Functional verification (requires Pi):**
   - App starts without errors
   - Screen timeout still works (screen turns off after configured time)
   - Touch wakes screen
   - Pattern execution works
   - UI is responsive

3. **Performance verification (requires Pi):**
   - Run `htop` or `top` while app is idle for 60 seconds
   - CPU usage should be < 20%

---

## Success Criteria

- [ ] No console.log in main.qml MouseArea handlers
- [ ] No debug console.log in QML component files
- [ ] Screen timeout uses single-shot timer (event-driven)
- [ ] WebSocket handler has no routine print statements
- [ ] Preview paths are cached after first lookup
- [ ] All changes committed with atomic commits

---

## Output

- Modified files in `dune-weaver-touch/`
- 6 commits following the pattern `{type}(01-01): {description}`
- SUMMARY.md created after execution
