# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Factory Inventory Management System: a Claude Code workshop demo. Vue 3 frontend, FastAPI backend, in-memory mock data loaded from JSON (no database, no auth). `client/CLAUDE.md` and `server/CLAUDE.md` hold longer per-side conventions and load automatically when you work inside those folders.

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. `client/.npmrc` pins the public npm registry and `client/package-lock.json` is gitignored to prevent locally-configured registries from leaking into commits — leave both in place.

## Commands

```bash
# Backend (FastAPI on :8001, Swagger at /docs). Requires uv and Python >= 3.11.
cd server && uv sync && uv run python main.py

# Frontend (Vite on :3000)
cd client && npm install && npm run dev

# Both at once (macOS/Linux only; logs in /tmp/inventory-*.log)
./scripts/start.sh
./scripts/stop.sh

# Production bundle -> client/dist/
cd client && npm run build
```

Backend tests must run from `server/` so `uv run` finds the venv (there is no pyproject in `tests/`, so `cd tests && uv run pytest` fails). `tests/pytest.ini` supplies the config and `tests/backend/conftest.py` puts `server/` on `sys.path` and imports `app` directly, so no server needs to be running.

```bash
cd server && uv run pytest ../tests                       # all (54 tests, <1s)
cd server && uv run pytest ../tests/backend/test_inventory.py
cd server && uv run pytest "../tests/backend/test_inventory.py::TestInventoryEndpoints::test_get_all_inventory"
cd server && uv run pytest ../tests --cov=. --cov-report=html
```

There are no frontend tests and no linter or type checker configured on either side. `tests/README.md` and `tests/TEST_SUMMARY.md` list a `test_orders.py` and higher test counts that no longer match the tree.

## Tool usage rules

- **vue-expert** subagent: MANDATORY for creating or significantly modifying any `.vue` file. **code-reviewer** after significant code; **Explore** for codebase questions.
- **backend-api-test** skill when writing or modifying anything under `tests/backend/`.
- **GitHub MCP** (`mcp__github__*`) for all GitHub operations except local branch creation (`git checkout -b`). Needs `GITHUB_PERSONAL_ACCESS_TOKEN` in the environment (see `.mcp.json`).
- **Playwright MCP** (`mcp__playwright__*`) for browser testing against `http://localhost:3000` and `http://localhost:8001`.
- Slash commands: `/start`, `/stop`, `/test`, `/demo-branch`, `/reset-branch` (destructive: deletes the branch, closes its PRs, discards the working tree), `/optimize`.

## Architecture

**Backend is one file.** `server/main.py` defines the Pydantic models, the two filter helpers and every route. `server/mock_data.py` loads each `server/data/*.json` once at import time into module-level lists; routes filter those lists in memory and nothing is ever written back, so a restart resets state. The only mutable state is the module-level `restocking_orders` list, which the restocking POST appends to and a restart clears. Read routes declare `response_model`, which means a field added to a JSON file is silently dropped from responses until the matching Pydantic model gains it.

**Filtering.** `apply_filters` handles `warehouse` (exact match), `category` and `status` (case-insensitive). `filter_by_month` matches the `month` param against `order_date` as a substring, accepting either `YYYY-MM` or a quarter key from `QUARTER_MAP` (`Q1-2025`..`Q4-2025`, hard-coded to 2025). Only orders and the dashboard summary take `month`; inventory, demand and backlog have no time dimension. The `/api/reports/*` endpoints aggregate orders by quarter and month with their own inline logic and take no filters.

**Frontend data flow.** `client/src/composables/useFilters.js` keeps the four filter refs (period, location, category, status) at module scope, so every caller shares one singleton. `FilterBar.vue` writes them, and each view `watch`es only the subset it cares about and refetches through `client/src/api.js` (Dashboard and Orders react to all four; Inventory, Demand and Backlog to location and category; Spending to period only). `getCurrentFilters()` maps the UI `period` to the API `month` param, and `api.js` drops any value equal to `'all'` before sending. Views hold raw API arrays in refs and derive everything else (status counts, on-time rate, category totals) in computed properties. `Reports.vue` bypasses `api.js` and calls axios with the hard-coded URL itself.

**API base URL is hard-coded** to `http://localhost:8001/api` in `api.js`; there is no Vite proxy, and the backend allows all CORS origins.

**Routing.** `client/src/main.js` registers `/`, `/inventory`, `/orders`, `/demand`, `/spending`, `/reports`, `/restocking`. `views/Backlog.vue` exists but has no route; backlog data is shown through the Dashboard modals.

**i18n and currency.** A hand-rolled `useI18n.js` (no vue-i18n) with `en` and `ja` dictionaries in `client/src/locales/`. Missing `ja` keys fall back to English, then to the key string, so every new UI string needs an entry in both files. Switching to `ja` also switches the currency: `utils/currency.js` converts stored USD amounts with a fixed 150 JPY rate at display time. Product names, customer names and warehouse names are translated by helper functions in `useI18n.js`, not by the locale files. `useAuth.js` is a mock user whose profile and task list are also locale-dependent.

**Restocking.** `GET /api/restocking/recommendations?budget=` joins demand forecasts with inventory by SKU (which is why every forecast SKU must exist in `inventory.json`), takes the forecast gap as the order quantity, sorts by gap descending and greedily marks items `recommended` while their line total fits the remaining budget, skipping rather than truncating. `POST /api/restocking/orders` creates a `Submitted` order whose lead time is the slowest line's category lead time from `LEAD_TIME_DAYS`, and `GET /api/restocking/orders` lists them newest first. `views/Restocking.vue` drives the slider and order button; `Orders.vue` shows them in a separate Submitted Orders card that ignores the shared filters.

**Endpoints the client calls that do not exist.** `api.js` has methods for `/api/tasks` (GET, POST, PATCH, DELETE) and `/api/purchase-orders` (POST, GET by backlog item id). `main.py` defines `CreatePurchaseOrderRequest` and reads `purchase_orders.json` (currently `[]`) to flag backlog items, but neither route is implemented, so the Tasks modal only shows the mock tasks and logs a fetch error to the console.

## Data vocabulary

Values must match the JSON files exactly or filters return nothing:

- Warehouses: `San Francisco`, `London`, `Tokyo`
- Categories: `Circuit Boards`, `Sensors`, `Actuators`, `Controllers`, `Power Supplies`
- Order statuses: `Delivered`, `Shipped`, `Processing`, `Backordered`
- Dates are `YYYY-MM-DDTHH:MM:SS` strings in 2025 (restocking orders use the real current date)
- Demand forecast SKUs must all exist in `inventory.json`; a test enforces this, and `stable` forecasts must change by under 2%

`server/generate_data.py` regenerates `orders.json` from its own product catalog (Widgets, Bearings, Motors...), which does not match the categories and SKUs in the current data files. Do not run it without first aligning its catalog with `inventory.json`.

## Conventions and gotchas

- Always document non-obvious logic changes with comments.
- Use stable `v-for` keys (`sku`, `month`, `id`), never the index.
- Guard date math: check `actual_delivery` / `expected_delivery` exist before building `Date` objects.
- Dashboard revenue goal is $800K per month, or $9.6M when the period is `all`; the other KPI goals are literals in the template.
- Design system: slate/gray palette (`#0f172a`, `#64748b`, `#e2e8f0`), green/blue/yellow/red for status, custom SVG charts, CSS Grid layouts, global styles in `client/src/App.vue`, no emojis in the UI.
