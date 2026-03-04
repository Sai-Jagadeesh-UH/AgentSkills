# Deployment Reference — FastAPI

## Table of Contents
1. [Uvicorn Configuration & Debugging](#uvicorn-config)
2. [Gunicorn + Uvicorn (Production)](#gunicorn-uvicorn)
3. [Docker — Standard Container](#docker-standard)
4. [Docker — Multi-Stage Build](#docker-multistage)
5. [Docker Compose (Local Dev)](#docker-compose)
6. [Azure Container Apps](#azure-container-apps)
7. [Azure Function App](#azure-function-app)
8. [AWS Lambda (Mangum)](#aws-lambda)
9. [Health & Readiness Endpoints](#health-endpoints)
10. [Environment Configuration](#environment-config)

---

## Uvicorn Configuration & Debugging {#uvicorn-config}

### Development — Uvicorn with Auto-Reload

```bash
# Basic dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# With detailed logging
uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level debug \
  --access-log \
  --use-colors

# Watch additional directories for reload
uvicorn app.main:app \
  --reload \
  --reload-dir app \
  --reload-dir config \
  --reload-include "*.py" \
  --reload-include "*.env"
```

### Uvicorn Programmatic Launch (for debugging in IDE)

Create `run.py` in project root — allows breakpoints and debugger attachment:

```python
# run.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,               # auto-reload on code changes
        reload_dirs=["app"],       # directories to watch
        log_level="debug",         # debug | info | warning | error
        access_log=True,           # log all requests
        use_colors=True,
        proxy_headers=False,       # set True behind nginx/traefik
        forwarded_allow_ips="*",   # IPs allowed to set X-Forwarded-For
        timeout_keep_alive=5,      # keep-alive timeout seconds
        limit_concurrency=100,     # max concurrent connections
        limit_max_requests=None,   # restart after N requests (memory leak prevention)
    )
```

### VS Code Debugger Configuration

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI: Debug",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/run.py",
      "console": "integratedTerminal",
      "env": {
        "PYTHONPATH": "${workspaceFolder}",
        "ENVIRONMENT": "development"
      },
      "justMyCode": false
    },
    {
      "name": "FastAPI: Attach to Process",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      }
    }
  ]
}
```

### Remote Debug via debugpy

```python
# Attach debugger remotely (e.g., in Docker)
import debugpy
debugpy.listen(("0.0.0.0", 5678))
print("Waiting for debugger attach on port 5678...")
debugpy.wait_for_client()  # pause until debugger attached

uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
```

### Uvicorn SSL (local HTTPS)

```bash
# Generate self-signed cert
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Run with SSL
uvicorn app.main:app --ssl-keyfile key.pem --ssl-certfile cert.pem --port 8443
```

### Uvicorn Logging Configuration

```python
# logging_config.py
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if not settings.debug else "default",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "uvicorn": {"level": "INFO", "propagate": False},
        "uvicorn.access": {"level": "INFO", "propagate": False},
        "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
    },
}

# In run.py
uvicorn.run("app.main:app", log_config=LOGGING_CONFIG)
```

### Request ID Middleware (Debugging)

```python
import uuid
from fastapi import Request

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

### Uvicorn Config File

Create `uvicorn.toml` or use `gunicorn.conf.py`:

```toml
# uvicorn.toml (for uvicorn CLI)
[uvicorn]
host = "0.0.0.0"
port = 8000
workers = 1
log_level = "info"
access_log = true
proxy_headers = true
```

---

## Gunicorn + Uvicorn (Production) {#gunicorn-uvicorn}

```bash
pip install gunicorn uvicorn[standard]
```

### gunicorn.conf.py

```python
# gunicorn.conf.py
import multiprocessing

# Worker configuration
workers = multiprocessing.cpu_count() * 2 + 1  # formula for I/O-bound APIs
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Binding
bind = "0.0.0.0:8000"
backlog = 2048

# Timeouts
timeout = 120           # worker timeout (increase for slow endpoints)
graceful_timeout = 30   # graceful shutdown time
keepalive = 5

# Memory management
max_requests = 1000         # restart worker after N requests
max_requests_jitter = 100   # randomize restart to avoid thundering herd

# Logging
loglevel = "info"
accesslog = "-"       # stdout
errorlog = "-"        # stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# Process naming
proc_name = "fastapi-app"

# Lifecycle hooks
def on_starting(server):
    print("Gunicorn master starting...")

def post_fork(server, worker):
    print(f"Worker spawned (pid: {worker.pid})")

def worker_exit(server, worker):
    print(f"Worker exiting (pid: {worker.pid})")
```

### Start command

```bash
gunicorn app.main:app -c gunicorn.conf.py
```

---

## Docker — Standard Container {#docker-standard}

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Security: don't run as root
RUN addgroup --system app && adduser --system --group app

WORKDIR /app

# Layer cache optimization: deps before code
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY --chown=app:app . .

USER app

EXPOSE 8000

# Exec form required for proper signal handling + lifespan events
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
```

### Using uv (fast Python package manager)

```dockerfile
FROM python:3.12-slim
RUN pip install uv
COPY pyproject.toml uv.lock .
RUN uv sync --frozen --no-dev
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Docker — Multi-Stage Build {#docker-multistage}

```dockerfile
# Dockerfile.multistage — minimizes final image size
FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install uv
COPY pyproject.toml uv.lock .
RUN uv sync --frozen --no-dev --compile-bytecode

# Production stage
FROM python:3.12-slim AS production

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=app:app app/ ./app/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini .

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
```

### .dockerignore

```
__pycache__/
*.pyc
*.pyo
.git/
.venv/
.env
.env.*
!.env.example
tests/
.pytest_cache/
*.egg-info/
dist/
.coverage
htmlcov/
*.log
node_modules/
.DS_Store
```

---

## Docker Compose (Local Dev) {#docker-compose}

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./app:/app/app  # hot reload in dev
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:password@db:5432/appdb
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=true
      - ENVIRONMENT=development
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - app-network

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: appdb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d appdb"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --save 60 1 --loglevel warning
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - app-network

  # Optional: Adminer for DB management UI
  adminer:
    image: adminer
    ports:
      - "8080:8080"
    networks:
      - app-network
    profiles:
      - tools

volumes:
  postgres_data:
  redis_data:

networks:
  app-network:
    driver: bridge
```

---

## Azure Container Apps {#azure-container-apps}

```yaml
# azure-container-app.yaml (ARM / Bicep equivalent in YAML)
# Deploy with: az containerapp create ...

name: my-fastapi-app
resourceGroup: my-rg
location: eastus

containerapp:
  image: myregistry.azurecr.io/fastapi-app:latest
  targetPort: 8000
  ingress:
    external: true
    transport: http

  scale:
    minReplicas: 1
    maxReplicas: 10
    rules:
      - name: http-rule
        http:
          metadata:
            concurrentRequests: "100"  # scale when >100 concurrent requests

  resources:
    cpu: 0.5
    memory: 1Gi

  env:
    - name: DATABASE_URL
      secretRef: db-connection-string
    - name: REDIS_URL
      secretRef: redis-connection-string

  secrets:
    - name: db-connection-string
      keyVaultUrl: https://myvault.vault.azure.net/secrets/db-url
      identity: system
```

### Deploy Commands

```bash
# Login and set ACR
az login
az acr login --name myregistry

# Build and push
docker build -t myregistry.azurecr.io/fastapi-app:latest .
docker push myregistry.azurecr.io/fastapi-app:latest

# Deploy Container App
az containerapp create \
  --name my-fastapi-app \
  --resource-group my-rg \
  --environment my-env \
  --image myregistry.azurecr.io/fastapi-app:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars "DATABASE_URL=secretref:db-url" \
  --secrets "db-url=postgresql+asyncpg://..."

# Update image
az containerapp update \
  --name my-fastapi-app \
  --resource-group my-rg \
  --image myregistry.azurecr.io/fastapi-app:v2.0.0
```

### Dapr Integration (for microservices)

```python
# Dapr service invocation — no code change needed
# Dapr sidecar handles service discovery, retries, observability
# Access state store
import httpx

async def save_state(key: str, value: dict):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"http://localhost:3500/v1.0/state/statestore",
            json=[{"key": key, "value": value}]
        )
```

---

## Azure Function App {#azure-function-app}

Azure Functions supports ASGI-compatible frameworks via `func.AsgiFunctionApp`. The official pattern (from Azure Samples) wraps your FastAPI app directly.

### File Structure

```
project/
├── function_app.py          ← ASGI bridge (root level, required)
├── host.json                ← Functions host config (routePrefix = "")
├── requirements.txt         ← azure-functions + fastapi + your deps
├── local.settings.json      ← local dev config (NOT committed)
└── WrapperFunction/         ← your FastAPI app module
    ├── __init__.py          ← defines the FastAPI app
    └── ...                  ← routers, models, etc.
```

### function_app.py (root)

```python
# function_app.py — the ASGI bridge
import azure.functions as func
from WrapperFunction import app as fastapi_app

# http_auth_level controls who can call the function:
# ANONYMOUS: no key needed (handle auth in FastAPI middleware)
# FUNCTION: requires function-level key
# ADMIN: requires master key
app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS,
)
```

### WrapperFunction/__init__.py

```python
# WrapperFunction/__init__.py — full FastAPI app
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.router import api_router
from app.config import get_settings

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — keep lightweight for cold start speed
    print("Function app starting...")
    yield
    print("Function app shutting down...")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.include_router(api_router)
```

### host.json

```json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": ""
    }
  },
  "logging": {
    "logLevel": {
      "default": "Information",
      "Host.Results": "Error",
      "Function": "Information",
      "Host.Aggregator": "Trace"
    }
  }
}
```

### requirements.txt

```
azure-functions
fastapi
pydantic-settings
pyjwt
pwdlib[argon2]
httpx
# Add your specific deps here
```

### local.settings.json (DO NOT COMMIT)

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ENVIRONMENT": "development",
    "DEBUG": "true",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
    "SECRET_KEY": "dev-only-secret-key"
  }
}
```

### .gitignore additions for Functions

```gitignore
local.settings.json
.azure/
__azurite_db_*.json
```

### Local Development & Testing

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Create and activate venv
python -m venv .venv && source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Start local Functions host
func start

# Test endpoints
# http://localhost:7071/sample
# http://localhost:7071/api/v1/users/
```

### Deployment Options

```bash
# Option 1: Azure CLI
az login
az functionapp create \
  --name my-fastapi-func \
  --resource-group my-rg \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4 \
  --os-type linux \
  --storage-account mystorageacct

func azure functionapp publish my-fastapi-func

# Option 2: Azure Developer CLI (provisions everything)
azd init
azd up

# Option 3: GitHub Actions CI/CD
azd pipeline config  # sets up GitHub Actions workflow
```

### Cold Start Optimization

Azure Functions cold starts are the main performance concern. Minimize them:

```python
# WrapperFunction/__init__.py — cold start optimizations

# 1. Lazy imports at module level
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 2. Singleton pattern for expensive resources
_db_engine = None

def get_db_engine():
    global _db_engine
    if _db_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import get_settings
        _db_engine = create_async_engine(get_settings().database_url)
    return _db_engine

# 3. Keep the FastAPI app instance at module level (reused across warm invocations)
app = FastAPI(lifespan=lifespan)

# 4. Use Premium Plan or Container App for always-warm instances
# (Consumption plan has most cold start impact)
```

### Choosing the Right Azure Hosting

| Option | Cold Start | Cost | Scale | When to Use |
|---|---|---|---|---|
| Functions (Consumption) | ~2-5s | Pay per call | Auto | Low traffic, event-driven |
| Functions (Premium) | None (pre-warm) | Higher | Auto | Consistent traffic, VNet |
| Container Apps | ~1-2s | Pay per hour | Auto | Complex apps, sidecars |
| AKS | None | Highest | Manual/KEDA | Enterprise, full control |

---

## AWS Lambda / Google Cloud Run (Mangum) {#aws-lambda}

```bash
pip install mangum
```

```python
# handler.py
from mangum import Mangum
from app.main import app

# Lambda handler
handler = Mangum(app, lifespan="off")  # or "auto"

# With custom settings
handler = Mangum(
    app,
    lifespan="off",
    api_gateway_base_path="/v1",  # if mounted under path
)
```

```yaml
# serverless.yml (Serverless Framework)
service: fastapi-service
provider:
  name: aws
  runtime: python3.12
  region: us-east-1
  environment:
    DATABASE_URL: !Sub "postgresql+asyncpg://..."

functions:
  app:
    handler: handler.handler
    events:
      - httpApi:
          path: /{proxy+}
          method: ANY
      - httpApi:
          path: /
          method: ANY
    layers:
      - arn:aws:lambda:us-east-1:...:layer:PythonDeps:1
```

---

## Health & Readiness Endpoints {#health-endpoints}

Required for Kubernetes/Container Apps liveness and readiness probes:

```python
# api/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, UTC
import redis.asyncio as aioredis

router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    """Basic liveness check — always returns 200 if process is alive"""
    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}

@router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness check — verifies DB and Redis connectivity"""
    checks = {}
    status = "ready"

    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        status = "not_ready"

    # Check Redis if configured
    if settings.redis_url:
        try:
            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            status = "not_ready"

    code = 200 if status == "ready" else 503
    return JSONResponse(
        status_code=code,
        content={"status": status, "checks": checks}
    )

@router.get("/live")
async def liveness():
    """Kubernetes liveness probe — minimal check"""
    return {"alive": True}
```

---

## Environment Configuration {#environment-config}

### .env.example (commit this, not .env)

```env
# Application
APP_NAME="FastAPI App"
APP_VERSION="1.0.0"
ENVIRONMENT=production
DEBUG=false

# Security — generate with: openssl rand -hex 32
SECRET_KEY=CHANGE_ME_GENERATE_WITH_OPENSSL

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Redis (optional)
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=300

# CORS
ALLOWED_ORIGINS=["https://myapp.com","https://www.myapp.com"]

# Azure (optional)
AZURE_TENANT_ID=
AZURE_CLIENT_ID=

# Uvicorn (when running directly)
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8000
UVICORN_WORKERS=4
```

### Reading config in pyproject.toml

```toml
[project]
name = "my-fastapi-app"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115.0",
    "pydantic-settings>=2.0",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "uvicorn[standard]>=0.30",
    "gunicorn>=22.0",
    "pyjwt>=2.8",
    "pwdlib[argon2]>=0.2",
    "redis[hiredis]>=5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "anyio>=4.0",
]

[tool.uvicorn]
host = "0.0.0.0"
port = 8000
reload = true
```
