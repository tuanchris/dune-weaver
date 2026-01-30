# Contributing to Dune Weaver

Thanks for your interest in contributing to Dune Weaver! Whether it's a bug fix, a new feature, or improved docs, every contribution helps make kinetic sand tables more accessible.

If you have questions or ideas, join the [#dev channel on Discord](https://discord.com/channels/864079106424832021/1329553521032560791) or browse the existing [Issues](https://github.com/tuanchris/dune-weaver/issues).

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Git

### Clone and install

```bash
git clone https://github.com/tuanchris/dune-weaver.git
cd dune-weaver

# Python dependencies (use nonrpi on a dev machine, full requirements.txt on a Raspberry Pi)
pip install -r requirements-nonrpi.txt

# Testing/dev extras
pip install -r requirements-dev.txt

# Frontend + root dependencies
npm install
cd frontend && npm install && cd ..
```

### Start the dev server

```bash
npm run dev
```

This runs **both** servers concurrently:

| Service  | URL                    | Notes                              |
| -------- | ---------------------- | ---------------------------------- |
| Frontend | `http://localhost:5173` | Vite dev server with hot reload   |
| Backend  | `http://localhost:8080` | FastAPI (proxied by Vite in dev)  |

Open `http://localhost:5173` in your browser. Vite proxies all API and WebSocket requests to the backend automatically.

## Project Structure

```
dune-weaver/
├── frontend/           # React 19 + TypeScript + Vite
│   ├── src/
│   │   ├── pages/      # Route-level page components
│   │   ├── components/ # Shared UI and feature components
│   │   ├── hooks/      # Custom React hooks
│   │   ├── lib/        # Utilities and API client
│   │   └── contexts/   # React contexts (multi-table, etc.)
│   └── package.json
├── modules/            # Backend modules
│   ├── core/           # Pattern/playlist managers, state, scheduling
│   ├── connection/     # Serial and WebSocket hardware communication
│   ├── led/            # WLED integration
│   └── mqtt/           # MQTT integration
├── patterns/           # .thr pattern files (theta-rho coordinates)
├── main.py             # FastAPI application entry point
└── package.json        # Root scripts (dev, build, prepare)
```

## Running Tests

### Backend (pytest)

```bash
pytest tests/unit/ -v
pytest tests/unit/ -v --cov       # with coverage
```

### Frontend (Vitest)

```bash
cd frontend && npm test           # single run
cd frontend && npm run test:watch # watch mode
cd frontend && npm run test:coverage
```

### End-to-end (Playwright)

```bash
cd frontend && npx playwright install chromium   # first time only
cd frontend && npm run test:e2e
cd frontend && npm run test:e2e:ui               # interactive UI mode
```

### Hardware Integration Tests (pytest)

Integration tests exercise real hardware — serial connections, homing, movement, and pattern execution. They are **skipped by default** and in CI.

```bash
# Run all integration tests (hardware must be connected via USB)
pytest tests/integration/ --run-hardware -v

# Run a specific suite
pytest tests/integration/test_hardware.py --run-hardware -v

# Show live output (useful for watching motor activity)
pytest tests/integration/ --run-hardware -v -s
```

| Test file | What it covers | Approx. duration |
| --------- | -------------- | ---------------- |
| `test_hardware.py` | Serial connection, homing, movement, pattern execution | ~5–10 min |
| `test_playback_controls.py` | Pause, resume, stop, skip, speed control | ~5 min |
| `test_playlist.py` | Playlist modes, clear patterns, state updates | ~5 min |

> **Safety:** These tests physically move the table. Make sure the ball path is clear and the table is powered on before running them.

## Linting

### Python — Ruff

```bash
ruff check .                # check for issues
ruff check --fix .          # auto-fix what it can
```

### Frontend — ESLint

```bash
cd frontend && npm run lint
```

### Pre-commit hook

A pre-commit hook runs Ruff on staged Python files and Vitest on staged TypeScript files automatically. It's installed when you run `npm install` at the repo root (via the `prepare` script). You can also install it manually:

```bash
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

## Branch and Commit Conventions

### Branching

Create branches from `main` using these prefixes:

- `feature/` — new functionality (e.g., `feature/pattern-editor`)
- `fix/` — bug fixes (e.g., `fix/playlist-reorder`)
- `chore/` — maintenance, tooling, docs (e.g., `chore/update-deps`)

### Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(ui): add dark mode toggle to settings page
fix(backend): prevent crash when serial port disconnects
chore: update Python dependencies
```

## Adding API Endpoints

When you add a new backend endpoint, you **must** also register its path in the Vite proxy so it works during development:

1. Add the route in `main.py` (or the appropriate module).
2. Open `frontend/vite.config.ts` and add the endpoint path to the `server.proxy` object:
   ```ts
   '/my_new_endpoint': 'http://localhost:8080',
   ```
3. Restart the Vite dev server (`npm run dev`).

> **Tip:** Endpoints under the `/api` prefix are already proxied by a single rule, so prefer using `/api/...` paths for new routes.

## Submitting a Pull Request

1. **Fork** the repository and clone your fork.
2. Create a branch from `main` (see [Branch and Commit Conventions](#branch-and-commit-conventions)).
3. Make sure all tests pass and linting is clean:
   ```bash
   ruff check .
   cd frontend && npm run lint && npm test && cd ..
   pytest tests/unit/ -v
   ```
4. Push your branch to your fork and open a PR against `main` on the upstream repo.
5. Fill in a clear description of **what** changed and **why**.
6. CI will run backend tests, frontend tests, E2E tests, and Ruff lint automatically.

Thanks for helping make Dune Weaver better!
