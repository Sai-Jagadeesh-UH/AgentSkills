# FastAPI Skill for Claude Code

A comprehensive Claude Code skill for building, testing, and deploying production-grade REST APIs with FastAPI.

## What It Does

When invoked, this skill guides you through the complete API development lifecycle:

1. **Project Analysis** — scans your existing codebase, identifies structure, finds anti-patterns
2. **Interactive Model Design** — collaboratively builds Pydantic v2 models through conversation
3. **API Design** — RESTful endpoint design following industry standards
4. **Authentication** — JWT, API Key, OAuth2, Azure AD / Entra ID
5. **Deployment** — Docker, Azure Functions, Azure Container Apps, AWS Lambda
6. **Performance** — async patterns, caching, Uvicorn/Gunicorn tuning, profiling
7. **Testing** — async test patterns with httpx and pytest
8. **UI Integration** — NiceGUI or Jinja2 templates with HTMX

## Skill Structure

```
skills/fastapi-skill/
├── SKILL.md                     ← Main skill instructions (loaded on trigger)
├── agents/
│   ├── project-analyzer.md      ← Deep project structure analysis
│   ├── model-designer.md        ← Interactive Pydantic model builder
│   └── api-designer.md          ← RESTful endpoint design & review
├── references/                  ← Loaded progressively as needed
│   ├── stack-internals.md       ← Starlette/Pydantic/FastAPI internals
│   ├── pydantic-patterns.md     ← Pydantic v2 patterns and validators
│   ├── api-design.md            ← RESTful design, pagination, error formats
│   ├── auth.md                  ← Auth implementations (JWT, API Key, Azure AD)
│   ├── async-patterns.md        ← Async, background tasks, WebSockets
│   ├── deployment.md            ← Docker, Azure Functions, Container Apps
│   ├── performance.md           ← Caching, optimization, load testing
│   ├── testing.md               ← pytest-asyncio, httpx, fixtures
│   ├── uvicorn-internals.md     ← Uvicorn config, debugging, workers
│   ├── package-internals.md     ← FastAPI/Starlette/Pydantic source analysis
│   └── ui-integration.md        ← NiceGUI and Jinja2 integration
├── scripts/
│   ├── analyze_project.py       ← Scan and report existing project structure
│   ├── generate_structure.py    ← Scaffold new project from template
│   └── validate_models.py       ← Check Pydantic models for common issues
└── assets/
    ├── docker-templates/
    │   ├── Dockerfile.uvicorn   ← Single process container
    │   ├── Dockerfile.gunicorn  ← Multi-worker production
    │   ├── gunicorn.conf.py     ← Gunicorn configuration
    │   └── docker-compose.yml   ← Local dev with PostgreSQL + Redis
    └── azure-templates/
        └── function-app/
            ├── function_app.py  ← ASGI bridge for Azure Functions
            ├── host.json        ← Azure Functions host config
            └── WrapperFunction/ ← FastAPI app module
```

## Triggering the Skill

The skill triggers on phrases like:
- "build an API with FastAPI"
- "create a Pydantic model for..."
- "add JWT authentication to my FastAPI app"
- "dockerize my FastAPI API"
- "deploy FastAPI to Azure Functions"
- "optimize my FastAPI performance"
- "design RESTful endpoints for..."
- "help me test my FastAPI app"

## Key Capabilities

### Pydantic v2 (Interactive)
The model-designer agent conducts an interview to understand your domain and generates production-ready Pydantic schemas with proper validation, field constraints, and schema separation (Create/Update/Read).

### Deployment Targets
- **Uvicorn** (dev/simple production)
- **Gunicorn + Uvicorn workers** (multi-CPU production)
- **Docker** (single or multi-stage builds)
- **Azure Functions** (ASGI via `AsgiFunctionApp`)
- **Azure Container Apps** (with scaling rules)
- **AWS Lambda** (via Mangum adapter)

### Authentication
Full implementations for:
- JWT Bearer tokens (HS256/RS256, access + refresh)
- API Key (header, hashed storage, rotation)
- OAuth2 / OpenID Connect
- Azure AD / Entra ID (MSAL, group-based RBAC)

### Async Optimization
- Async DB patterns (SQLAlchemy async, asyncpg)
- Parallel query execution with `asyncio.gather`
- Background tasks (native + ARQ + Celery)
- WebSockets and Server-Sent Events
- Streaming responses for large data

## Setup

```bash
# Run project analyzer on your existing project
python skills/fastapi-skill/scripts/analyze_project.py .

# Scaffold a new project
python skills/fastapi-skill/scripts/generate_structure.py \
    --name my-api \
    --target docker \
    --db postgresql \
    --auth jwt \
    --ui none

# Validate your Pydantic models
python skills/fastapi-skill/scripts/validate_models.py app/schemas/
```

## FastAPI Version

Tested with FastAPI 0.115+ (Pydantic v2 native, lifespan API).
The skill does NOT use deprecated patterns:
- X `@app.on_event` -> use `lifespan` context manager
- X `orm_mode = True` -> use `from_attributes=True` in `ConfigDict`
- X `tiangolo/uvicorn-gunicorn` base image -> use `python:3.12-slim` with explicit CMD
