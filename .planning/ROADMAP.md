# Roadmap — v3 Touch App CPU Optimization

**Milestone goal:** Reduce idle CPU usage from 100%+ to under 20% on Pi 3B+, Pi 4, and Pi 5.

---

## Phase 1: CPU Optimization ✅ COMPLETE

**Goal:** Eliminate all identified CPU hotspots and verify performance targets.

**Requirements covered:**
- REQ-LOG-01 through REQ-LOG-06 (QML logging cleanup)
- REQ-TIMER-01, REQ-TIMER-02 (Timer optimization)
- REQ-WS-01, REQ-WS-02 (WebSocket optimization)
- REQ-CACHE-01, REQ-CACHE-02 (Preview cache)
- REQ-VERIFY-01 through REQ-VERIFY-04 (Verification)

**Success criteria:**
- [x] No console.log in main.qml mouse/touch handlers
- [x] No debug console.log in QML component files
- [x] Screen timeout uses event-driven scheduling (not 1-sec polling)
- [x] WebSocket handler only emits signals on actual value changes
- [x] Pattern preview paths are cached after first lookup
- [ ] Idle CPU < 20% measured on Pi (requires hardware testing)
- [ ] UI remains responsive (requires hardware testing)

**Completed:** 2026-01-25

---

## Requirement Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-LOG-01 | 1 | ✅ Complete |
| REQ-LOG-02 | 1 | ✅ Complete |
| REQ-LOG-03 | 1 | ✅ Complete |
| REQ-LOG-04 | 1 | ✅ Complete |
| REQ-LOG-05 | 1 | ✅ Complete |
| REQ-LOG-06 | 1 | ✅ Complete |
| REQ-TIMER-01 | 1 | ✅ Complete |
| REQ-TIMER-02 | 1 | ⏳ Needs Pi test |
| REQ-WS-01 | 1 | ✅ Complete |
| REQ-WS-02 | 1 | ✅ Complete |
| REQ-CACHE-01 | 1 | ✅ Complete |
| REQ-CACHE-02 | 1 | ✅ Complete |
| REQ-VERIFY-01 | 1 | ⏳ Needs Pi test |
| REQ-VERIFY-02 | 1 | ⏳ Needs Pi test |
| REQ-VERIFY-03 | 1 | ⏳ Needs Pi test |
| REQ-VERIFY-04 | 1 | ⏳ Needs Pi test |

**Coverage:** 16/16 requirements addressed
**Code complete:** 12/16 (75%)
**Hardware verification pending:** 4/16 (25%)

---

## Completed Milestones

| Version | Name | Completed | Archive |
|---------|------|-----------|---------|
| v1 | Backend Testing | 2026-01-24 | [v1-backend-testing.md](milestones/v1-backend-testing.md) |
| v2 | Frontend Testing | 2026-01-25 | [v2-frontend-testing.md](milestones/v2-frontend-testing.md) |

---

*Updated: 2026-01-25*
