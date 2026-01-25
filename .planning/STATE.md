# Project State

## Current Position

Milestone: v2-frontend-testing
Phase: 04-e2e-ci (4 of 4)
Plan: 01 of 1 - COMPLETE
Status: Milestone complete
Last activity: 2026-01-25 - Completed 04-01-PLAN.md (E2E & CI)

Progress: [##########] 100%

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 01 | Test Infrastructure | **Complete** |
| 02 | Component Tests | **Complete** |
| 03 | Integration Tests | **Complete** |
| 04 | E2E & CI | **Complete** |

## Completed Milestones

| Version | Name | Completed | Archive |
|---------|------|-----------|---------|
| v1 | Backend Testing | 2026-01-24 | [v1-backend-testing.md](milestones/v1-backend-testing.md) |
| v2 | Frontend Testing | 2026-01-25 | (pending archive) |

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

## Blockers/Concerns

None currently.

## Session Continuity

Last session: 2026-01-25
Stopped at: Completed 04-01-PLAN.md (E2E & CI)
Resume file: None - milestone complete

## Test Summary

| Category | Tests |
|----------|-------|
| Component tests | 42 |
| Integration tests | 22 |
| E2E tests | 13 |
| **Total frontend tests** | **77** |
| Backend tests | 17 |
| **Grand total** | **94** |

## CI Coverage

GitHub Actions workflow runs:
- Backend: pytest with coverage
- Backend: Ruff linting
- Frontend: Vitest unit/integration tests
- Frontend: Playwright E2E tests
