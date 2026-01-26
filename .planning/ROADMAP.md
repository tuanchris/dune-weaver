# Roadmap — v3 Touch App CPU Optimization

**Milestone goal:** Reduce idle CPU usage from 100%+ to under 20% on Pi 3B+, Pi 4, and Pi 5.

---

## Phase 1: CPU Optimization

**Goal:** Eliminate all identified CPU hotspots and verify performance targets.

**Requirements covered:**
- REQ-LOG-01 through REQ-LOG-06 (QML logging cleanup)
- REQ-TIMER-01, REQ-TIMER-02 (Timer optimization)
- REQ-WS-01, REQ-WS-02 (WebSocket optimization)
- REQ-CACHE-01, REQ-CACHE-02 (Preview cache)
- REQ-VERIFY-01 through REQ-VERIFY-04 (Verification)

**Success criteria:**
- [ ] No console.log in main.qml mouse/touch handlers
- [ ] No debug console.log in QML component files
- [ ] Screen timeout uses event-driven scheduling (not 1-sec polling)
- [ ] WebSocket handler only emits signals on actual value changes
- [ ] Pattern preview paths are cached after first lookup
- [ ] Idle CPU < 20% measured on Pi (any model available for testing)
- [ ] UI remains responsive (no lag when scrolling patterns)

**Research needed:** No — fixes are straightforward code changes.

**Estimated scope:** Small (< 1 day) — mostly removing/modifying existing code.

---

## Requirement Coverage

| Requirement | Phase |
|-------------|-------|
| REQ-LOG-01 | 1 |
| REQ-LOG-02 | 1 |
| REQ-LOG-03 | 1 |
| REQ-LOG-04 | 1 |
| REQ-LOG-05 | 1 |
| REQ-LOG-06 | 1 |
| REQ-TIMER-01 | 1 |
| REQ-TIMER-02 | 1 |
| REQ-WS-01 | 1 |
| REQ-WS-02 | 1 |
| REQ-CACHE-01 | 1 |
| REQ-CACHE-02 | 1 |
| REQ-VERIFY-01 | 1 |
| REQ-VERIFY-02 | 1 |
| REQ-VERIFY-03 | 1 |
| REQ-VERIFY-04 | 1 |

**Coverage:** 16/16 requirements (100%)

---

## Completed Milestones

| Version | Name | Completed | Archive |
|---------|------|-----------|---------|
| v1 | Backend Testing | 2026-01-24 | [v1-backend-testing.md](milestones/v1-backend-testing.md) |
| v2 | Frontend Testing | 2026-01-25 | [v2-frontend-testing.md](milestones/v2-frontend-testing.md) |

---

*Created: 2026-01-25*
