# NiceGUI Docker Reference

## Table of Contents
1. [Official Image (quickest path)](#1-official-image-quickest-path)
2. [Custom Dockerfile (production)](#2-custom-dockerfile-production)
3. [Multi-stage Optimized Build](#3-multi-stage-optimized-build)
4. [docker-compose.yml Patterns](#4-docker-composeyml-patterns)
5. [.dockerignore](#5-dockerignore)
6. [Environment Variables & Secrets](#6-environment-variables--secrets)
7. [Volumes & Data Persistence](#7-volumes--data-persistence)
8. [Nginx Reverse Proxy](#8-nginx-reverse-proxy)
9. [Health Checks & Signal Handling](#9-health-checks--signal-handling)
10. [Build & Push Commands](#10-build--push-commands)

---

## 1. Official Image (quickest path)

The fastest way — use `zauberzeug/nicegui` from Docker Hub:

```yaml
# docker-compose.yml
services:
  nicegui:
    image: zauberzeug/nicegui:latest
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./app:/app          # mount your code into /app
    environment:
      - PUID=1000           # match your host user id: `id -u`
      - PGID=1000           # match your host group id: `id -g`
      - STORAGE_SECRET=change-this-to-your-own-private-secret
```

Your app code lives in `./app/main.py` — the container auto-runs it.

**When to use:** Prototypes, simple single-file apps, quick demos.
**When NOT to use:** Custom dependencies, production builds, multi-file apps.

---

## 2. Custom Dockerfile (production)

For apps with custom dependencies and project structure:

```dockerfile
# Dockerfile
FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Add only what you actually need:
    # libgl1          # OpenCV
    # libglib2.0-0    # OpenCV
    # libpq-dev       # PostgreSQL psycopg2
    && rm -rf /var/lib/apt/lists/*

# ── App user (non-root) ───────────────────────────────────────────────────────
RUN groupadd -r appuser && useradd -r -g appuser appuser

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first — Docker layer caches this if requirements.txt unchanged
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Static file directory ─────────────────────────────────────────────────────
RUN mkdir -p static .nicegui

# ── Ownership ─────────────────────────────────────────────────────────────────
RUN chown -R appuser:appuser /app
USER appuser

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8080

# Use exec form (not shell form) so signals pass through to Python
CMD ["python", "main.py"]
```

### `main.py` — production `ui.run()` settings
```python
import os
from nicegui import app, ui

# ... your pages and components ...

def handle_shutdown():
    print('Graceful shutdown initiated')
    # close DB connections, flush caches, etc.

app.on_shutdown(handle_shutdown)

ui.run(
    host='0.0.0.0',                          # bind all interfaces
    port=int(os.getenv('PORT', '8080')),
    title=os.getenv('APP_TITLE', 'My App'),
    storage_secret=os.environ['STORAGE_SECRET'],  # fail fast if missing
    reload=False,                             # NEVER True in Docker/prod
    show=False,                               # don't try to open browser
    dark=None,
)
```

---

## 3. Multi-stage Optimized Build

Reduces image size by separating build from runtime:

```dockerfile
# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir --upgrade pip

# Install dependencies into a virtual env (makes copying easy)
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# System libs (runtime only — no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

WORKDIR /app

# Copy venv from builder — no pip install needed in this stage
COPY --from=builder /opt/venv /opt/venv

# Copy application
COPY --chown=appuser:appuser . .

# Create data directories
RUN mkdir -p static .nicegui data \
 && chown -R appuser:appuser /app

USER appuser

# Activate the venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/_nicegui/heartbeat || exit 1

CMD ["python", "main.py"]
```

**Layer caching strategy:**
1. `requirements.txt` copied first → only reinstalled if it changes
2. App code copied after → changing `main.py` doesn't trigger pip install
3. Virtual env in `/opt/venv` → cleanly copyable between stages

---

## 4. docker-compose.yml Patterns

### Development (with live reload)
```yaml
# docker-compose.dev.yml
services:
  nicegui:
    build:
      context: .
      dockerfile: Dockerfile.dev
    ports:
      - "8080:8080"
    volumes:
      - .:/app            # mount entire project — reload works
    environment:
      - DEBUG=true
      - STORAGE_SECRET=dev-only-secret
      - PORT=8080
    env_file:
      - .env.dev
```

```dockerfile
# Dockerfile.dev
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Don't COPY code — it's mounted as a volume
CMD ["python", "main.py"]
```

### Production (immutable, no volume mounts)
```yaml
# docker-compose.yml
services:
  nicegui:
    image: myapp:latest             # pre-built image
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - app_data:/app/data          # only mount persistent data dir
      - app_nicegui:/app/.nicegui   # NiceGUI session storage
    environment:
      - PORT=8080
    env_file:
      - .env                        # production secrets
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/_nicegui/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'

volumes:
  app_data:
  app_nicegui:
```

### With Nginx reverse proxy + SSL
```yaml
services:
  nicegui:
    image: myapp:latest
    expose:
      - "8080"              # internal only — nginx forwards to this
    env_file: .env
    restart: unless-stopped
    volumes:
      - app_data:/app/data
      - nicegui_storage:/app/.nicegui

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./static:/var/www/static:ro  # serve static files directly
    depends_on:
      - nicegui
    restart: unless-stopped

volumes:
  app_data:
  nicegui_storage:
```

---

## 5. .dockerignore

Always create this — prevents bloating the build context:

```dockerignore
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/
.env/

# NiceGUI runtime data (regenerated)
.nicegui/

# Development data
data/*.db
data/*.sqlite
*.db

# Secrets (never send to Docker daemon)
.env
.env.*
*.key
*.pem
*.p12

# Version control
.git/
.gitignore

# IDE
.vscode/
.idea/
*.swp

# Testing
tests/
.pytest_cache/
htmlcov/
.coverage

# Documentation
docs/
*.md
README*

# Node (if any frontend tooling)
node_modules/
```

---

## 6. Environment Variables & Secrets

### `.env` file (never in image)
```env
STORAGE_SECRET=your-64-char-random-secret-here
PORT=8080
APP_TITLE=My App
DEBUG=false
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/myapp
OPENAI_API_KEY=sk-...
```

### In `docker-compose.yml`
```yaml
services:
  nicegui:
    env_file:
      - .env              # loaded from file (not in image)
    environment:
      - NODE_ENV=production   # additional env vars
```

### Docker Secrets (Swarm mode / production)
```yaml
services:
  nicegui:
    secrets:
      - storage_secret
    environment:
      - STORAGE_SECRET_FILE=/run/secrets/storage_secret

secrets:
  storage_secret:
    file: ./secrets/storage_secret.txt
```

```python
# Read from file in production
import os

def load_secret(env_var: str) -> str:
    file_path = os.getenv(f'{env_var}_FILE')
    if file_path:
        return open(file_path).read().strip()
    return os.environ[env_var]

STORAGE_SECRET = load_secret('STORAGE_SECRET')
```

---

## 7. Volumes & Data Persistence

### What to persist
| Path | What it contains | Persist? |
|------|-----------------|---------|
| `/app/.nicegui` | Session storage (`app.storage.user`) | Yes |
| `/app/data/` | SQLite databases, uploaded files | Yes |
| `/app/static/` | Static assets (if generated at runtime) | Maybe |
| `/app/*.py` | Code | No — bake into image |
| `/app/requirements.txt` | Dependencies | No — bake into image |

```yaml
volumes:
  - nicegui_storage:/app/.nicegui    # user session persistence
  - app_data:/app/data               # databases, uploads
```

### Backup strategy
```bash
# Backup .nicegui storage
docker cp container_name:/app/.nicegui ./backup/.nicegui

# Backup SQLite DB
docker cp container_name:/app/data/app.db ./backup/app.db
```

---

## 8. Nginx Reverse Proxy

### `nginx/nginx.conf` for NiceGUI

NiceGUI requires WebSocket pass-through:

```nginx
upstream nicegui {
    server nicegui:8080;
}

server {
    listen 80;
    server_name example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Serve static files directly (bypass NiceGUI for better performance)
    location /static/ {
        alias /var/www/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # NiceGUI app (including WebSocket)
    location / {
        proxy_pass http://nicegui;
        proxy_http_version 1.1;

        # WebSocket required headers
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-lived WebSocket connections
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

### Subpath hosting (app at `/myapp/`)
```python
# In main.py — tell NiceGUI it's mounted at a subpath
ui.run(
    host='0.0.0.0',
    port=8080,
    uvicorn_kwargs={'root_path': '/myapp'},
)
```

```nginx
location /myapp/ {
    proxy_pass http://nicegui/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

---

## 9. Health Checks & Signal Handling

### Health check endpoint
```python
from nicegui import app

@app.get('/health')
async def health():
    return {'status': 'ok', 'version': '1.0.0'}
```

### Graceful shutdown (handle SIGTERM)
```python
import signal, asyncio
from nicegui import app, ui

async def graceful_shutdown():
    print('SIGTERM received — shutting down gracefully')
    # Close DB connections, flush queues, etc.
    await Tortoise.close_connections()

def handle_sigterm(*args):
    asyncio.create_task(graceful_shutdown())

signal.signal(signal.SIGTERM, handle_sigterm)

# OR use NiceGUI's built-in hook
app.on_shutdown(lambda: print('NiceGUI shutdown'))
```

### Docker HEALTHCHECK in Dockerfile
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
```

---

## 10. Build & Push Commands

```bash
# Build the image
docker build -t myapp:latest .
docker build -t myapp:1.2.0 .

# Multi-platform build (for M1 Mac → Linux server)
docker buildx build --platform linux/amd64 -t myapp:latest .

# Run locally
docker run -p 8080:8080 --env-file .env myapp:latest

# Run with docker-compose
docker compose up                    # foreground
docker compose up -d                 # detached
docker compose up -d --build         # rebuild and start
docker compose logs -f nicegui       # follow logs

# Push to registry
docker tag myapp:latest registry.example.com/myapp:latest
docker push registry.example.com/myapp:latest

# Cleanup
docker compose down
docker compose down -v               # also remove volumes
docker image prune -f                # remove dangling images
```

### Build checklist before deploying
- [ ] `reload=False` in `ui.run()`
- [ ] `show=False` in `ui.run()`
- [ ] `host='0.0.0.0'` in `ui.run()`
- [ ] `STORAGE_SECRET` comes from env var, not hardcoded
- [ ] `.dockerignore` created (especially `.env` excluded)
- [ ] Health check endpoint `/health` returns 200
- [ ] `CMD` uses exec form `["python", "main.py"]` not shell form
- [ ] Non-root user in container
- [ ] Persistent volumes mounted for `.nicegui/` and `data/`
- [ ] WebSocket proxied correctly if behind Nginx
