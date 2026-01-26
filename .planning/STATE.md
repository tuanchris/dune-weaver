# Project State

## Current Position

Milestone: v3 Touch App CPU Optimization
Phase: 1 — CPU Optimization
Plan: Not yet created (run /gsd:plan-phase 1)
Status: Ready to plan
Last activity: 2026-01-25 — Roadmap created

Progress: Phase 1 of 1

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

## Blockers/Concerns

None currently.

## Session Continuity

Last session: 2026-01-25
Stopped at: Created v3 roadmap
Resume file: None

## v3 Milestone Context

**Target:** < 20% CPU when idle on Pi 3B+, Pi 4, Pi 5

**Phase 1 covers all 16 requirements:**
- QML logging cleanup (6 requirements)
- Timer optimization (2 requirements)
- WebSocket optimization (2 requirements)
- Preview cache (2 requirements)
- Verification (4 requirements)
