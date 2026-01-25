# Project State

## Current Position

Milestone: None active
Status: Ready for new milestone
Last activity: 2026-01-25 — Completed v2-frontend-testing

Progress: N/A

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

## Blockers/Concerns

None currently.

## Session Continuity

Last session: 2026-01-25
Stopped at: Completed v2-frontend-testing milestone
Resume file: None

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
