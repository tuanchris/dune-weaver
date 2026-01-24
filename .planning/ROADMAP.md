# Roadmap: Frontend Testing (v2)

**Milestone:** v2 Frontend Testing
**Created:** 2026-01-24
**Phases:** 4

## Overview

```
Phase 01: Test Infrastructure ──► Phase 02: Component Tests ──► Phase 03: Integration Tests ──► Phase 04: E2E & CI
   (INF-1,2,3,4)                    (CMP-1,2,3,4)                  (INT-1,2,3)                    (E2E-1, INF-5)
```

---

## Phase 01: Test Infrastructure

**Goal:** Set up Vitest, Playwright, and MSW so tests can be written

**Requirements:**
- INF-1: Vitest configured with jsdom environment and React Testing Library
- INF-2: Playwright installed with Chrome browser configuration
- INF-3: MSW (Mock Service Worker) configured for API mocking
- INF-4: Test directory structure established

**Status:** ✅ Complete

**Success Criteria:**
- [x] `npm test` runs Vitest and exits cleanly (even with 0 tests)
- [x] `npm run test:e2e` runs Playwright and exits cleanly
- [x] MSW handlers can intercept `/api/*` requests in tests
- [x] Directory structure: `frontend/src/__tests__/`, `frontend/e2e/`

**Research needed:** None (standard Vite + Vitest setup)

**Estimated plans:** 1

---

## Phase 02: Component Tests

**Goal:** Test critical pages in isolation with mocked API

**Requirements:**
- CMP-1: BrowsePage tests — pattern listing, selection, search/filter
- CMP-2: PlaylistsPage tests — playlist CRUD, drag-drop reordering
- CMP-3: NowPlayingBar tests — playback state, controls
- CMP-4: TableControlPage tests — manual controls, homing, position

**Success Criteria:**
- [ ] BrowsePage: renders pattern list, clicking pattern triggers selection callback
- [ ] PlaylistsPage: renders playlists, drag-drop reorders items, CRUD buttons work
- [ ] NowPlayingBar: displays current track, play/pause/stop buttons trigger handlers
- [ ] TableControlPage: control buttons render, homing button triggers API call

**Research needed:** May need to research dnd-kit testing patterns

**Estimated plans:** 1-2

---

## Phase 03: Integration Tests

**Goal:** Test multi-component user flows with mocked backend

**Requirements:**
- INT-1: Pattern flow — browse → select → run → verify API
- INT-2: Playlist flow — create → add patterns → reorder → run → verify API
- INT-3: Playback flow — start → pause → resume → stop → verify state

**Success Criteria:**
- [ ] Pattern flow: user can browse, select pattern, click run, API called with correct pattern
- [ ] Playlist flow: user can create playlist, add patterns, reorder, run playlist
- [ ] Playback flow: user can control playback, state transitions correctly reflected in UI

**Research needed:** None (extends component test patterns)

**Estimated plans:** 1

---

## Phase 04: E2E & CI

**Goal:** Validate real browser experience and automate in CI

**Requirements:**
- E2E-1: Critical user journey in real browser
- INF-5: GitHub Actions workflow extended for frontend tests

**Success Criteria:**
- [ ] E2E test: complete flow from browse → play pattern → UI shows playing state
- [ ] CI: `npm test` runs in GitHub Actions on PR
- [ ] CI: `npm run test:e2e` runs in GitHub Actions (headless Chrome)
- [ ] CI: Frontend tests complete in < 5 minutes

**Research needed:** None (extends existing CI from backend testing)

**Estimated plans:** 1

---

## Requirement Coverage Matrix

| Requirement | Phase | Status |
|-------------|-------|--------|
| INF-1 | 01 | ✅ Complete |
| INF-2 | 01 | ✅ Complete |
| INF-3 | 01 | ✅ Complete |
| INF-4 | 01 | ✅ Complete |
| INF-5 | 04 | Pending |
| CMP-1 | 02 | Pending |
| CMP-2 | 02 | Pending |
| CMP-3 | 02 | Pending |
| CMP-4 | 02 | Pending |
| INT-1 | 03 | Pending |
| INT-2 | 03 | Pending |
| INT-3 | 03 | Pending |
| E2E-1 | 04 | Pending |

**Coverage:** 13/13 requirements mapped (100%)

---

## Phase Dependencies

```
01 ─────────► 02 ─────────► 03
 │                           │
 └───────────────────────────┴──► 04
```

- Phase 02 depends on Phase 01 (need test infrastructure)
- Phase 03 depends on Phase 02 (builds on component test patterns)
- Phase 04 depends on 01 and 03 (needs infrastructure + tests to run in CI)

---

## Milestone Definition of Done

- [ ] All 13 requirements satisfied
- [ ] All 4 phases complete with VERIFICATION.md
- [ ] `npm test` passes with 20+ component/integration tests
- [ ] `npm run test:e2e` passes with 3+ E2E tests
- [ ] GitHub Actions runs all tests on every PR
- [ ] Test suite completes in < 5 minutes
