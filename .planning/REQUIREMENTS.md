# Requirements — v3 Touch App CPU Optimization

**Goal:** Reduce idle CPU usage from 100%+ to under 20% on Raspberry Pi 3B+, Pi 4, and Pi 5.

**Verification method:** Run touch app idle for 60 seconds, measure CPU with `htop` or `top`.

---

## v3 Requirements (In Scope)

### Category: QML Logging Cleanup

- [ ] **REQ-LOG-01**: Remove console.log from onPositionChanged handler in main.qml
  - Keep `backend.resetActivityTimer()` call
  - Delete only the logging statement

- [ ] **REQ-LOG-02**: Remove console.log from onPressed handler in main.qml
  - Keep `backend.resetActivityTimer()` call

- [ ] **REQ-LOG-03**: Remove console.log from onClicked handler in main.qml
  - Keep `backend.resetActivityTimer()` call

- [ ] **REQ-LOG-04**: Remove all debug console.log from ConnectionStatus.qml
  - Lines with "ConnectionStatus:" prefix

- [ ] **REQ-LOG-05**: Remove all debug console.log from ExecutionPage.qml
  - Lines with "ExecutionPage:" prefix and image status logs

- [ ] **REQ-LOG-06**: Audit and remove debug logs from other QML files
  - ModernPatternListPage.qml
  - PatternDetailPage.qml
  - TableControlPage.qml
  - LedControlPage.qml
  - ModernPlaylistPage.qml

### Category: Timer Optimization

- [ ] **REQ-TIMER-01**: Convert screen timeout from polling to event-driven
  - Current: 1-second QTimer checking `_check_screen_timeout()` continuously
  - Target: Only schedule timeout check after activity detected
  - Location: backend.py:140-152

- [ ] **REQ-TIMER-02**: Ensure screen timeout still works correctly after refactor
  - Screen should turn off after configured timeout period
  - Touch should wake screen
  - No regression in functionality

### Category: WebSocket Optimization

- [ ] **REQ-WS-01**: Reduce redundant signal emissions in `_on_ws_message`
  - Only emit signals when values actually change
  - Location: backend.py:310-364

- [ ] **REQ-WS-02**: Remove or reduce print statements in WebSocket handler
  - Keep error logging, remove routine status logging

### Category: Preview Cache Optimization

- [ ] **REQ-CACHE-01**: Cache pattern preview paths after first lookup
  - Add dictionary to store `filename → preview_path` mappings
  - Location: backend.py `_find_pattern_preview()` method

- [ ] **REQ-CACHE-02**: Invalidate cache appropriately
  - Clear cache when patterns are refreshed
  - Don't cache negative results (missing previews)

### Category: Verification

- [ ] **REQ-VERIFY-01**: Measure idle CPU on Pi 3B+ < 20%
  - App running, no user interaction, for 60 seconds

- [ ] **REQ-VERIFY-02**: Measure idle CPU on Pi 4 < 20%
  - App running, no user interaction, for 60 seconds

- [ ] **REQ-VERIFY-03**: Measure idle CPU on Pi 5 < 20%
  - App running, no user interaction, for 60 seconds

- [ ] **REQ-VERIFY-04**: Verify no UI lag during normal operation
  - Scrolling pattern list remains smooth
  - Touch response remains immediate

---

## v4 / Future (Out of Scope)

- Debug flag system for conditional logging
- Performance test automation
- CPU monitoring dashboard in app
- Memory optimization
- Startup time optimization

---

## Summary

| Category | v3 Count | Deferred |
|----------|----------|----------|
| QML Logging | 6 | 0 |
| Timer Optimization | 2 | 0 |
| WebSocket Optimization | 2 | 0 |
| Preview Cache | 2 | 0 |
| Verification | 4 | 0 |
| **Total** | **16** | **0** |

---

*Created: 2026-01-25*
