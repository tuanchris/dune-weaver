# Phase 04 Plan 01: E2E Tests and GitHub Actions Integration Summary

**One-liner:** Playwright E2E tests with WebSocket mocking for critical user journeys, plus GitHub Actions CI integration for frontend tests.

## Completed Work

### Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1.1 | Playwright API mock utilities | ddc463c | e2e/mocks/api.ts |
| 2.1 | Pattern flow E2E tests | dd4baaf | e2e/pattern-flow.spec.ts |
| 2.2 | Playlist flow E2E tests | 647cb08 | e2e/playlist-flow.spec.ts |
| 2.3 | Table control E2E tests | 8406243 | e2e/table-control.spec.ts |
| 3.1 | Update sample spec | 449034a | e2e/sample.spec.ts |
| 4.1 | Extend CI workflow | 9207135 | .github/workflows/test.yml |
| 5.1-5.2 | Test fixes and verification | fa94d6a | api.ts, playwright.config.ts, tests |

### Test Counts

| Category | Tests |
|----------|-------|
| App infrastructure (sample.spec.ts) | 3 |
| Pattern flow (pattern-flow.spec.ts) | 4 |
| Playlist flow (playlist-flow.spec.ts) | 3 |
| Table control (table-control.spec.ts) | 3 |
| **Total E2E tests** | **13** |
| Component tests (Phase 02) | 42 |
| Integration tests (Phase 03) | 22 |
| **Total frontend tests** | **77** |

### Key Files Created/Modified

**Created:**
- `frontend/e2e/mocks/api.ts` - Playwright route mocking with WebSocket support
- `frontend/e2e/pattern-flow.spec.ts` - Pattern browsing and execution E2E tests
- `frontend/e2e/playlist-flow.spec.ts` - Playlist viewing and execution E2E tests
- `frontend/e2e/table-control.spec.ts` - Table control page E2E tests

**Modified:**
- `frontend/e2e/sample.spec.ts` - Updated with meaningful infrastructure tests
- `frontend/playwright.config.ts` - Added dedicated E2E port (5174) to avoid conflicts
- `.github/workflows/test.yml` - Added frontend-test and frontend-e2e jobs

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| WebSocket mocking via routeWebSocket() | Required to bypass blocking "Connecting to Backend" overlay |
| Dedicated port 5174 for E2E | Avoids conflict with other dev servers running on 5173 |
| Playwright route interception | More reliable than MSW for E2E (MSW requires service worker in browser) |
| Button locators by title/exact name | Avoids strict mode violations with multiple similar buttons |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] WebSocket connection blocks UI**
- **Found during:** Task 5.1 verification
- **Issue:** App shows blocking overlay until WebSocket /ws/status connects
- **Fix:** Added `page.routeWebSocket()` mocking for all WebSocket endpoints
- **Files modified:** e2e/mocks/api.ts
- **Commit:** fa94d6a

**2. [Rule 3 - Blocking] Port conflict with other dev server**
- **Found during:** Task 5.1 verification
- **Issue:** Port 5173 already in use by another project (Image2Dune)
- **Fix:** Changed Playwright config to use dedicated port 5174
- **Files modified:** playwright.config.ts
- **Commit:** fa94d6a

**3. [Rule 1 - Bug] Run playlist API field name mismatch**
- **Found during:** Task 5.1 verification
- **Issue:** Mock expected `name` but actual API sends `playlist_name`
- **Fix:** Updated mock to accept both field names
- **Files modified:** e2e/mocks/api.ts
- **Commit:** fa94d6a

## Requirements Addressed

- [x] **E2E-1:** Critical user journey - browse -> play pattern -> verify UI updates
- [x] **INF-5:** GitHub Actions workflow extended to run frontend tests alongside backend
- [x] 3+ E2E tests (milestone target: 3+, actual: 13)
- [x] CI: `npm test` runs Vitest tests in GitHub Actions
- [x] CI: `npm run test:e2e` runs Playwright tests in GitHub Actions
- [x] CI: Frontend tests configured with appropriate timeout (< 10 minutes)

## CI Workflow Summary

The `.github/workflows/test.yml` now includes:

| Job | Description | Timeout |
|-----|-------------|---------|
| test | Backend Python tests with pytest | default |
| lint | Backend Python linting with Ruff | default |
| frontend-test | Vitest unit/integration tests | default |
| frontend-e2e | Playwright E2E tests (Chromium) | 10 minutes |

Features:
- Node.js 20 with npm caching
- Playwright browsers installed in CI
- Report artifacts uploaded on failure
- Triggered on push to main/feature/*, PRs to main
- Includes `frontend/**` in path triggers

## Next Phase Readiness

Phase 04 is complete. This completes the v2-frontend-testing milestone.

**Milestone Summary:**
- Phase 01: Test infrastructure (Vitest, RTL, MSW, Playwright)
- Phase 02: Component tests (42 tests)
- Phase 03: Integration tests (22 tests)
- Phase 04: E2E tests and CI (13 E2E tests, CI workflow)

**Total Test Coverage:**
- Backend: 17 tests (from v1)
- Frontend: 77 tests (64 Vitest + 13 Playwright)
- **Grand total: 94 tests**

## Metrics

| Metric | Value |
|--------|-------|
| Start time | 2026-01-25T14:43:03Z |
| End time | 2026-01-25T14:52:00Z |
| Duration | ~9 minutes |
| Tasks completed | 7/7 |
| E2E tests added | 13 |
| Files created | 5 |
| Files modified | 3 |
