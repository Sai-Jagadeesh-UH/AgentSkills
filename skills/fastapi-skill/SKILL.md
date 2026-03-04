---
name: fastapi-skill
description: Expert FastAPI REST API development skill. Triggers on: "build an API", "FastAPI", "REST endpoint", "Pydantic model", "API authentication", "dockerize API", "serverless API", "Azure Function API", "Container App", "API testing", "OpenAPI spec", "async API", "JWT auth", "OAuth2", "API performance", "high traffic API", "rate limit", "API cost", "capacity planning", "SLA", "scale API", NiceGUI/Jinja2 integration, routing, middleware, background tasks, WebSockets.
---

# FastAPI Skill

Expert FastAPI architect. Build, optimize, and deploy production-grade REST APIs. **Understand first, build second. Every decision has cost, reliability, and operational implications.**

Stack: FastAPI (DI + OpenAPI) → Starlette (routing/middleware/ASGI) → Pydantic v2 (Rust validation) → Uvicorn (ASGI server).
> Load `references/stack-internals.md` for architecture. `references/package-internals.md` for DI/middleware internals. `references/uvicorn-internals.md` for server config.
> Load `references/official-patterns.md` for canonical FastAPI best practices (Annotated style, return types, CLI, async rules, preferred libraries).

---

## Phase 0: Scan Project (ALWAYS FIRST)

```bash
python skills/fastapi-skill/scripts/analyze_project.py .
```

Use `agents/project-analyzer.md` to identify: structure gaps, tech stack, deployment hints, existing patterns, UI layer. Present findings, confirm before proceeding.

**FastAPI CLI** — use instead of bare uvicorn in development:
```bash
fastapi dev    # auto-reload (reads entrypoint from pyproject.toml)
fastapi run   # production
```
```toml
[tool.fastapi]  # pyproject.toml
entrypoint = "my_app.main:app"
```

---

## Phase 1: Requirements (ask only what's unanswered)

| Area | Options |
|------|---------|
| **Deployment** | local / docker / Azure Container App / Azure Function App / Lambda / gunicorn+nginx |
| **Auth** | none / API Key / JWT / OAuth2 / Azure AD — RBAC? |
| **DB** | SQLAlchemy async / SQLModel / Tortoise — PostgreSQL / MySQL / SQLite / Cosmos |
| **Scale** | peak RPS, read vs write heavy, caching (Redis?), background jobs? |
| **SLA** | availability target (99% / 99.9% / 99.99%)? latency budget (P95)? |
| **Budget** | monthly infra ceiling? reserved vs on-demand? |
| **UI** | NiceGUI / Jinja2+HTMX / none (pure API) |
| **Entities** | domain name, core resources, existing schema? |

---

## Phase 1.5: Engineering Design Review

**Run for all production APIs.** Skip only for local/dev-only builds.

Use `agents/engineering-advisor.md` to produce before writing any code:

1. **Capacity Analysis** — workers, pool size, memory per instance from RPS+latency targets
2. **Deployment Recommendation** — ranked options with estimated monthly cost and trade-offs
3. **Constraint Proposal** — rate limits (per tier/endpoint), payload limits, timeouts, SLA targets
4. **Risk Register** — top 5 risks with mitigations (N+1, cold start, connection exhaustion, etc.)
5. **Phased Build Plan** — MVP → GA → Scale milestones

> Load `references/cost-and-capacity.md` for deployment cost tables, break-even math, and sizing formulas.
> Load `references/rate-limiting.md` for constraint negotiation, algorithm selection, and SLA design.

**Challenge assumptions**: Rate limits protect business continuity. Cold starts breach SLAs. N+1 queries kill databases. Negotiate constraints *before* writing code — retrofitting is 10× more expensive.

---

## Phase 2: Project Structure

Standard structure (container/server): `app/{main,config,dependencies,exceptions}.py` + `api/v1/` + `core/` + `models/` + `schemas/` + `services/` + `repositories/` + optional `ui/`.

Azure Function App → see `references/deployment.md#azure-function`.

Scaffold after confirming:
```bash
python skills/fastapi-skill/scripts/generate_structure.py --name <project> --target <deployment>
```

---

## Phase 3: Pydantic Models (interactive)

For each entity ask: fields+types, optional vs required, computed fields, validators, relationships, Create/Update/Read split, sensitive fields to exclude.

Patterns: `AppBaseModel` with shared `ConfigDict`, `Annotated[T, Field(...)]`, `@field_validator`, `@model_validator`, schema split (`Base`→`Create`/`Update`/`Read`).

**Canonical code style** (from official FastAPI patterns):
- `Annotated[T, Field(...)]` everywhere — never bare `field: str = Field(...)`
- No ellipsis: `Field(gt=0)` not `Field(..., gt=0)`; required fields need no default
- No `RootModel` — use `Annotated` type + FastAPI creates `TypeAdapter` internally
- `Decimal` for money, `UUID` for public IDs, `str(Enum)` for constrained strings

**Negotiate model constraints** (from Phase 1.5 risk register):
- `max_length` on all string fields — prevent 100MB payloads
- `Decimal` for money (never `float`)
- UUID vs int ID — UUID for public APIs (no enumeration attacks)
- Enum vs free string — enum is safer for known value sets
- Flat vs nested — flat serializes faster, nested is cleaner for complex types

> Load `references/pydantic-patterns.md` for full examples, ORM integration, common pitfalls.
> Load `references/rate-limiting.md#model-negotiation` for field-by-field constraint checklist.

Validate after writing:
```bash
python skills/fastapi-skill/scripts/validate_models.py app/schemas/
```

Use `agents/model-designer.md` for complex multi-entity domains.

---

## Phase 4: API Design

RESTful: `GET /v1/{resources}` (list+paginate), `POST` (201), `GET /{id}`, `PUT` (full), `PATCH` (partial), `DELETE` (204). **One function per HTTP method** — never `api_route(methods=["GET","POST"])`.

Set `prefix`, `tags`, `dependencies` on `APIRouter(...)` itself — not in `app.include_router()`.

Confirm: pagination strategy (offset vs cursor), filtering, bulk ops, long-running (→ 202 + job ID), real-time (WebSocket/SSE), versioning (/v1).

Key status codes: 200/201/204, 400/401/403/404/409/422/429.

**Apply engineering constraints**: All list endpoints paginated. All POST endpoints idempotency-key capable. Expensive endpoints (`/export`, `/report`) get stricter per-endpoint rate limits.

> Load `references/api-design.md` for response envelopes, error format, pagination schemas.
> Load `references/rate-limiting.md` for per-endpoint limit patterns and idempotency implementation.

Use `agents/api-designer.md` for endpoint table generation and RESTful review.
Use `agents/engineering-advisor.md` Mode 2 (Red Team) to critique the proposed design.

---

## Phase 5: Authentication & Authorization

Auth type from Phase 1 drives implementation. Always propose RBAC unless auth=none.

> Load `references/auth.md` for: API Key (hashed), JWT (HS256/RS256 + refresh), OAuth2+PKCE, Azure AD/Entra ID (MSAL), RBAC, distributed rate limiting per API key.

---

## Phase 6: Performance & Async

Priority order: declare return types (Pydantic Rust serialization) → `response_model_exclude_unset` → async I/O → BackgroundTasks → Redis cache → connection pool (sized from Phase 1.5) → streaming → GZip → uvloop+httptools.

**`ORJSONResponse` is deprecated** — use `-> ReturnType` annotations instead; Pydantic handles Rust serialization automatically.

Async rule: use `async def` only when calling awaitable code. Use plain `def` for blocking/sync — FastAPI runs it in a thread pool automatically. When mixing, use **Asyncer** (`asyncify()` / `syncify()`).

Bottleneck: I/O-bound (asyncio/gather, Asyncer) vs CPU-bound (`asyncify` with ProcessPoolExecutor)?

Apply high-traffic checklist from `agents/engineering-advisor.md` Mode 4 before finalizing.

> Load `references/async-patterns.md`: gather/TaskGroup, Semaphore, ARQ queue, SSE, WebSocket manager.
> Load `references/performance.md`: ORJSONResponse, fastapi-cache2, N+1 fix, Locust/k6, Prometheus.
> Load `references/cost-and-capacity.md`: worker sizing, pool sizing, Redis cache ROI.
> Load `references/uvicorn-internals.md`: uvloop, httptools, worker count formula, VS Code debugger.

---

## Phase 7: Deployment

Copy templates:
```bash
cp skills/fastapi-skill/assets/docker-templates/Dockerfile.{uvicorn|gunicorn} ./Dockerfile
cp skills/fastapi-skill/assets/docker-templates/docker-compose.yml ./
cp -r skills/fastapi-skill/assets/azure-templates/function-app/ ./  # Azure Functions
```

Use deployment recommendation from Phase 1.5. Present cost comparison if still undecided.

> Load `references/deployment.md`: Dockerfile (multi-stage), docker-compose (PG+Redis), Azure Function App (`func.AsgiFunctionApp`), Container Apps, Lambda (Mangum), Gunicorn formula, health endpoints, debugpy.
> Load `references/cost-and-capacity.md`: deployment cost table, break-even analysis, min replicas vs scale-to-zero, reserved instance savings.

---

## Phase 8: UI Integration

**NiceGUI**: `ui.run_with(app)` for same-process; separate httpx client for decoupled. Share Pydantic schemas.
**Jinja2+HTMX**: `StaticFiles` mount + `Jinja2Templates`; HTMX for partial swaps.

> Load `references/ui-integration.md` for full patterns.

---

## Phase 9: Testing

```bash
pytest tests/ -v --asyncio-mode=auto --cov=app
```

Include load test at 3× expected peak (Locust template in `agents/engineering-advisor.md` Mode 4).

> Load `references/testing.md` for conftest, fixtures, mock patterns (respx, pytest-mock).

---

## Phase 10: Handoff

Deliver: architecture diagram (text), endpoint table, rate limit table, `.env.example` vars, run commands (dev/prod/docker/tests), estimated monthly cost at expected traffic, next steps (migrations/monitoring/cost alerts/rate limit tuning after 30d data).

---

## Resources (load on demand)

| Reference | Load when |
|-----------|-----------|
| `references/official-patterns.md` | writing any FastAPI code — canonical do/don't patterns, CLI, async rules, libraries |
| `references/stack-internals.md` | architecture questions, request lifecycle |
| `references/package-internals.md` | DI internals, middleware order, Pydantic Rust core |
| `references/uvicorn-internals.md` | server config, logging, debugger, SSL, worker tuning |
| `references/cost-and-capacity.md` | deployment costs, capacity math, break-even, sizing |
| `references/rate-limiting.md` | rate limiting patterns, constraint negotiation, SLA design |
| `references/pydantic-patterns.md` | model design, validators, ORM, settings |
| `references/api-design.md` | endpoint design, pagination, error format, versioning |
| `references/auth.md` | API Key, JWT, OAuth2, Azure AD, RBAC |
| `references/async-patterns.md` | async ops, Asyncer, SSE, JSON Lines, WebSocket, queues |
| `references/performance.md` | return-type serialization, caching, streaming, profiling |
| `references/deployment.md` | Docker, Azure Functions, Container Apps, Lambda |
| `references/testing.md` | test setup, fixtures, load testing |
| `references/ui-integration.md` | NiceGUI or Jinja2+HTMX |

| Agent | Use when |
|-------|----------|
| `agents/project-analyzer.md` | Phase 0 deep project analysis |
| `agents/engineering-advisor.md` | Phase 1.5 capacity/cost/SLA review; Phase 4+ red team critique |
| `agents/model-designer.md` | complex multi-entity Pydantic design |
| `agents/api-designer.md` | endpoint table generation, RESTful review |

| Script | Command |
|--------|---------|
| `scripts/analyze_project.py` | `python ... <path>` |
| `scripts/generate_structure.py` | `python ... --name X --target Y` |
| `scripts/validate_models.py` | `python ... app/schemas/` |
