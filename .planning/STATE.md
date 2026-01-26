# Project State

## Current Position

Milestone: v3 Touch App CPU Optimization
Phase: 1 — CPU Optimization ✅ COMPLETE
Plan: All plans executed
Status: Phase complete, awaiting hardware verification
Last activity: 2026-01-25 — Phase 1 executed and verified

Progress: Phase 1 of 1 complete

## Completed Milestones

| Version | Name | Completed | Archive |
|---------|------|-----------|---------|
| v1 | Backend Testing | 2026-01-24 | [v1-backend-testing.md](milestones/v1-backend-testing.md) |
| v2 | Frontend Testing | 2026-01-25 | [v2-frontend-testing.md](milestones/v2-frontend-testing.md) |

## Accumulated Decisions

| Decision | Context | Date |
|----------|---------|------|
| pytest + pytest-asyncio | Test framework selection for async FastAPI testing | 2026-01-24 |
| httpx for API testing | Standard FastAPI testing approach with ASGITransport | 2026-01-24 |
| CI=true env var | Hardware test auto-skip mechanism | 2026-01-24 |
| relative_files = true | Coverage config for CI compatibility | 2026-01-24 |
| Vitest + RTL | Frontend component testing framework | 2026-01-24 |
| Playwright | E2E browser automation | 2026-01-24 |
| MSW | API mocking at network level | 2026-01-24 |
| Extend existing CI | Run frontend tests in same workflow as backend | 2026-01-24 |
| vitest globals | Enable describe/it/expect without imports | 2026-01-24 |
| MSW onUnhandledRequest: warn | Changed from error due to WebSocket conflicts | 2026-01-25 |
| Chromium only (initial) | Faster CI, can add browsers later | 2026-01-24 |
| Observable behavior testing | Focus on what renders, clicks, API calls not implementation | 2026-01-25 |
| apiCallLog for API verification | Track API calls in MSW handlers for integration test assertions | 2026-01-25 |
| Button finding via textContent | More reliable than getByRole for buttons with similar names | 2026-01-25 |
| WebSocket mocking via routeWebSocket | Required to bypass blocking "Connecting to Backend" overlay | 2026-01-25 |
| Dedicated port 5174 for E2E | Avoids conflict with other dev servers on 5173 | 2026-01-25 |
| Remove debug logs (not flag) | Decided to remove all debug console.log rather than add conditional flag | 2026-01-25 |
| Event-driven screen timeout | Replace 1-sec polling with event-driven timeout scheduling | 2026-01-25 |
| Single-shot QTimer | Screen timeout timer fires once after inactivity period | 2026-01-25 |
| Preview cache dictionary | Cache pattern preview paths to avoid repeated filesystem lookups | 2026-01-25 |

## Blockers/Concerns

**Hardware verification pending:** Need to test on actual Raspberry Pi to confirm CPU < 20%

## Session Continuity

Last session: 2026-01-25
Stopped at: Phase 1 complete, ready for milestone audit
Resume file: None

## v3 Phase 1 Summary

**Commits:** 6
- `e3b1f2a` - Remove MouseArea console.log spam
- `455ed5c` - Remove remaining debug logs from main.qml
- `bf3729e` - Remove debug logs from ConnectionStatus.qml
- `e1b5994` - Remove debug logs from ExecutionPage.qml
- `e2e0c82` - Remove debug logs from remaining QML files
- `bd48ed4` - Optimize timer, WebSocket, and preview cache

**Files modified:** 8
- main.qml, ConnectionStatus.qml, ExecutionPage.qml
- TableControlPage.qml, ModernPlaylistPage.qml
- ThemeManager.qml, BottomNavTab.qml
- backend.py

**Verification:** 6/6 must-haves passed (code inspection)
