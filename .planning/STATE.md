# Project State

## Current Position

Milestone: v2-frontend-testing
Phase: 01-test-infrastructure (1 of 4)
Plan: 01 of 1 - COMPLETE
Status: Phase 01 complete
Last activity: 2026-01-24 — Completed 01-01-PLAN.md

Progress: [##--------] 25%

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 01 | Test Infrastructure | **Complete** |
| 02 | Component Tests | Pending |
| 03 | Integration Tests | Pending |
| 04 | E2E & CI | Pending |

## Completed Milestones

| Version | Name | Completed | Archive |
|---------|------|-----------|---------|
| v1 | Backend Testing | 2026-01-24 | [v1-backend-testing.md](milestones/v1-backend-testing.md) |

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
| MSW onUnhandledRequest: error | Fail fast on unexpected API calls | 2026-01-24 |
| Chromium only (initial) | Faster CI, can add browsers later | 2026-01-24 |

## Blockers/Concerns

None currently.

## Session Continuity

Last session: 2026-01-24
Stopped at: Completed 01-01-PLAN.md (Test Infrastructure)
Resume file: None
