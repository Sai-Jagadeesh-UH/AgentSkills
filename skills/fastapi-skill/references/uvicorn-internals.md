# Uvicorn Internals — Config, Debugging & Deployment

> Source-level analysis of uvicorn 0.30+ configuration and internals.
> Uvicorn Config class lives at: `uvicorn/config.py`

## Table of Contents
1. [Complete Config Reference](#config-reference)
2. [Event Loop Options](#event-loop)
3. [HTTP Protocol Options](#http-protocols)
4. [WebSocket Options](#websocket-options)
5. [Logging Configuration](#logging-config)
6. [Reload & Development](#reload-dev)
7. [SSL/TLS](#ssl-tls)
8. [Programmatic Launch Patterns](#programmatic-launch)
9. [Debugging Patterns](#debugging)
10. [Process Architecture](#process-architecture)
11. [Worker Process (Uvicorn inside Gunicorn)](#gunicorn-workers)

---

## Complete Config Reference {#config-reference}

The `uvicorn.Config` class (from source) accepts these parameters:

```python
import uvicorn

uvicorn.run(
    # --- APP ---
    app="app.main:app",       # ASGI app string or callable
    factory=False,            # if True, app is a factory function (app())

    # --- BINDING ---
    host="127.0.0.1",         # "0.0.0.0" for all interfaces (production)
    port=8000,
    uds=None,                 # Unix domain socket path (alternative to host:port)
    fd=None,                  # File descriptor to listen on

    # --- WORKERS ---
    workers=None,             # Number of worker processes (1 by default)
                              # Reads WEB_CONCURRENCY env var if workers=None
                              # Cannot use with --reload

    # --- EVENT LOOP ---
    loop="auto",              # "auto" | "asyncio" | "uvloop" | "none"
                              # uvloop is ~2-4x faster than asyncio (Linux only)
                              # Install: pip install uvloop

    # --- HTTP PROTOCOL ---
    http="auto",              # "auto" | "h11" | "httptools"
                              # httptools is faster (C-based)
                              # Install: pip install httptools
    h11_max_incomplete_event_size=None,  # max HTTP header size (h11 only)

    # --- WEBSOCKETS ---
    ws="auto",                # "auto" | "none" | "websockets" | "wsproto"
    ws_max_size=16777216,     # max WebSocket message size (16MB default)
    ws_max_queue=32,          # max queued WebSocket messages
    ws_ping_interval=20.0,    # seconds between WebSocket pings
    ws_ping_timeout=20.0,     # seconds to wait for pong before disconnect
    ws_per_message_deflate=True,  # WebSocket compression

    # --- LIFESPAN ---
    lifespan="auto",          # "auto" | "on" | "off"
                              # "auto": detect lifespan support from app
                              # "on": always run lifespan events
                              # "off": skip lifespan events (Azure Functions)

    # --- RELOAD ---
    reload=False,             # auto-reload on file changes (dev only)
    reload_dirs=None,         # directories to watch (list or str)
    reload_delay=0.25,        # debounce delay in seconds
    reload_includes=None,     # glob patterns to include in watching
    reload_excludes=None,     # glob patterns to exclude from watching

    # --- LOGGING ---
    log_config=LOGGING_CONFIG,  # dict | str (path to .json/.yaml/ini)
    log_level=None,           # "critical" | "error" | "warning" | "info" | "debug" | "trace"
    access_log=True,          # log each request
    use_colors=None,          # colorize log output (auto-detect if None)

    # --- PROXY HEADERS ---
    proxy_headers=True,       # trust X-Forwarded-For, X-Forwarded-Proto headers
    forwarded_allow_ips=None, # IPs trusted to set X-Forwarded-* headers
                              # Defaults to "127.0.0.1", "FORWARDED_ALLOW_IPS" env var
                              # Use "*" to trust all (only when behind trusted LB)

    # --- SERVER HEADERS ---
    server_header=True,       # include "Server: uvicorn" response header
    date_header=True,         # include "Date" response header
    headers=None,             # additional response headers: [("X-Custom", "value")]

    # --- LIMITS ---
    limit_concurrency=None,   # max concurrent connections (503 if exceeded)
    limit_max_requests=None,  # restart after N requests (memory leak prevention)
    limit_max_requests_jitter=0,  # randomize max_requests by ±N

    # --- TIMEOUTS ---
    timeout_keep_alive=5,     # seconds to keep idle HTTP connections open
    timeout_notify=30,        # seconds to wait for worker shutdown notification
    timeout_graceful_shutdown=None,  # seconds for graceful shutdown (None = unlimited)
    timeout_worker_healthcheck=5,  # seconds between worker health checks

    # --- INTERFACE ---
    interface="auto",         # "auto" | "asgi3" | "asgi2" | "wsgi"

    # --- SSL/TLS ---
    ssl_keyfile=None,
    ssl_certfile=None,
    ssl_keyfile_password=None,
    ssl_version=ssl.PROTOCOL_TLS_SERVER,
    ssl_cert_reqs=ssl.CERT_NONE,
    ssl_ca_certs=None,
    ssl_ciphers="TLSv1",

    # --- ENVIRONMENT ---
    env_file=None,            # path to .env file (loaded via dotenv)
    root_path="",             # ASGI root_path for mount prefix (behind reverse proxy)
)
```

---

## Event Loop Options {#event-loop}

Uvicorn supports pluggable event loop backends. From source:

```python
LOOP_FACTORIES = {
    "none": None,
    "auto": "uvicorn.loops.auto:auto_loop_factory",     # uses uvloop if available
    "asyncio": "uvicorn.loops.asyncio:asyncio_loop_factory",
    "uvloop": "uvicorn.loops.uvloop:uvloop_loop_factory",  # requires pip install uvloop
}
```

### uvloop (Recommended for Linux Production)

```bash
pip install uvloop
```

```python
# uvloop is ~2-4x faster than asyncio on Linux
# Automatically used when installed + loop="auto"
uvicorn.run("app.main:app", loop="uvloop")

# Or in gunicorn.conf.py:
# uvloop is used automatically by UvicornWorker
```

**Note**: uvloop does NOT work on Windows. Use `loop="asyncio"` on Windows.

---

## HTTP Protocol Options {#http-protocols}

```python
HTTP_PROTOCOLS = {
    "auto": "uvicorn.protocols.http.auto:AutoHTTPProtocol",
    "h11": "uvicorn.protocols.http.h11_impl:H11Protocol",       # pure Python
    "httptools": "uvicorn.protocols.http.httptools_impl:HttpToolsProtocol",  # C-based, faster
}
```

```bash
pip install httptools  # C-based HTTP parser (2-3x faster for high throughput)
```

```python
# When installed, httptools is used automatically (auto)
uvicorn.run("app.main:app", http="httptools")  # explicit
```

---

## WebSocket Options {#websocket-options}

```python
WS_PROTOCOLS = {
    "auto": "uvicorn.protocols.websockets.auto:AutoWebSocketsProtocol",
    "none": None,              # disable WebSocket support
    "websockets": "...",       # pip install websockets
    "wsproto": "...",          # pip install wsproto (alternative)
    "websockets-sansio": "...", # sansio variant
}
```

For production WebSocket performance:
- Use `websockets` (default when installed)
- Tune `ws_max_size` for your message payload sizes
- Reduce `ws_ping_interval` for better connection health detection

---

## Logging Configuration {#logging-config}

Uvicorn's default logging config (from source):

```python
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",  # custom formatter with level prefix
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,  # auto-detect
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
        "access": {"formatter": "access", "class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}
```

### Custom Logging Config

```python
# JSON structured logging for production
PROD_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",  # pip install python-json-logger
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "uvicorn": {"level": "INFO", "propagate": True},
        "uvicorn.access": {"level": "INFO", "propagate": True},
        "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
    },
}

uvicorn.run("app.main:app", log_config=PROD_LOGGING)
```

### Log Levels Available
From source: `"critical" | "error" | "warning" | "info" | "debug" | "trace"`

The `trace` level (not in standard Python logging) shows raw ASGI messages — useful for protocol debugging.

```bash
# CLI — enable trace level for deepest debugging
uvicorn app.main:app --log-level trace
```

---

## Reload & Development {#reload-dev}

```python
# Development server with fine-grained reload control
uvicorn.run(
    "app.main:app",
    reload=True,
    reload_dirs=["app", "config"],      # watch these directories
    reload_includes=["*.py", "*.env"],  # watch these patterns
    reload_excludes=["*.pyc"],          # ignore these patterns
    reload_delay=0.25,                  # debounce delay (seconds)
    log_level="debug",
)
```

**Note from source**: `workers > 1` is ignored when `reload=True`. Reload and multi-process are mutually exclusive.

### Watching Non-Python Files

```bash
# Watch templates and .env changes
uvicorn app.main:app --reload \
  --reload-include "*.html" \
  --reload-include "*.jinja2" \
  --reload-include ".env" \
  --reload-dir app \
  --reload-dir templates
```

---

## SSL/TLS {#ssl-tls}

```python
# Local HTTPS development
# 1. Generate self-signed cert:
# openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

uvicorn.run(
    "app.main:app",
    ssl_keyfile="key.pem",
    ssl_certfile="cert.pem",
    port=8443,
)
```

**Production**: Use Nginx/Traefik/Azure Front Door for TLS termination. Don't expose Uvicorn with SSL directly.

---

## Programmatic Launch Patterns {#programmatic-launch}

### run.py — IDE Debuggable

```python
# run.py — place in project root
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        log_level="debug",
        access_log=True,
        use_colors=True,
        loop="auto",           # uvloop if available
        http="auto",           # httptools if available
        proxy_headers=False,   # True only behind nginx/traefik
        timeout_keep_alive=5,
    )
```

### Config-Driven Launch

```python
# Separate config from launch
from uvicorn import Config, Server

config = Config(
    app="app.main:app",
    host="0.0.0.0",
    port=8000,
    log_level="info",
    loop="uvloop",
    http="httptools",
    workers=4,
    limit_max_requests=1000,
    limit_max_requests_jitter=100,
    timeout_graceful_shutdown=30,
)

server = Server(config=config)

# Can run programmatically
import asyncio
asyncio.run(server.serve())
```

### WEB_CONCURRENCY Environment Variable

From source: `if workers is None and "WEB_CONCURRENCY" in os.environ: self.workers = int(os.environ["WEB_CONCURRENCY"])`

```bash
# Heroku/PaaS pattern — set via env var
WEB_CONCURRENCY=4 uvicorn app.main:app
```

---

## Debugging Patterns {#debugging}

### VS Code Debugger

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI: Debug Server",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/run.py",
      "console": "integratedTerminal",
      "env": {
        "PYTHONPATH": "${workspaceFolder}",
        "ENVIRONMENT": "development",
        "DEBUG": "true"
      },
      "justMyCode": false  // step into library code
    },
    {
      "name": "FastAPI: Attach",
      "type": "debugpy",
      "request": "attach",
      "connect": {"host": "localhost", "port": 5678}
    }
  ]
}
```

### Remote Debug in Docker

```python
# run_debug.py — attach debugger before starting
import debugpy

debugpy.listen(("0.0.0.0", 5678))
print("Debugger listening on port 5678. Attach now...")
debugpy.wait_for_client()  # pause until debugger attached

import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
```

```dockerfile
# Dockerfile.debug
FROM python:3.12-slim
WORKDIR /app
RUN pip install debugpy
COPY . .
EXPOSE 8000 5678
CMD ["python", "run_debug.py"]
```

```yaml
# docker-compose.debug.yml
services:
  api:
    ports:
      - "8000:8000"
      - "5678:5678"  # debugger port
```

### TRACE Level — Protocol Debug

```bash
# See raw ASGI messages (very verbose)
uvicorn app.main:app --log-level trace
```

Output shows each ASGI message:
```
TRACE: ('http.request', {'body': b'{"email":"a@b.com"}', 'more_body': False})
TRACE: ('http.response.start', {'status': 200, 'headers': [...]})
TRACE: ('http.response.body', {'body': b'{"id":1}', 'more_body': False})
```

### Request Timing Middleware

```python
import time
from fastapi import Request

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    if duration_ms > 500:
        import logging
        logging.getLogger("app.performance").warning(
            f"Slow request: {request.method} {request.url.path} took {duration_ms:.0f}ms"
        )
    return response
```

### asyncio Debug Mode

```python
# Detect blocking calls in async functions
import asyncio
import logging

# Enable asyncio debug — logs coroutines taking >100ms
asyncio.get_event_loop().set_debug(True)
logging.getLogger("asyncio").setLevel(logging.DEBUG)

uvicorn.run("app.main:app", loop="asyncio")
```

---

## Process Architecture {#process-architecture}

### Single Process (Default)
```
uvicorn main:app
└── Event Loop (asyncio/uvloop)
    └── ASGI Application (FastAPI)
        ├── Middleware Stack
        ├── Router
        └── Endpoint
```

### Multi-Process (--workers)
```
uvicorn main:app --workers 4
└── Uvicorn Master Process
    ├── Worker 1 (Event Loop)
    ├── Worker 2 (Event Loop)
    ├── Worker 3 (Event Loop)
    └── Worker 4 (Event Loop)
```

Workers use `os.fork()`. Each has its own event loop and memory space.

### Gunicorn + Uvicorn Workers (Production)
```
gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4
└── Gunicorn Master (process manager, no I/O)
    ├── UvicornWorker 1 (Event Loop)
    ├── UvicornWorker 2 (Event Loop)
    ├── UvicornWorker 3 (Event Loop)
    └── UvicornWorker 4 (Event Loop)
```

Gunicorn adds: worker monitoring, graceful restart, max_requests recycling, SIGTERM handling.

**When to use each:**

| Scenario | Recommended |
|---|---|
| Development | `uvicorn --reload` (single process) |
| Simple production (1 server) | `uvicorn --workers $((2*CPU+1))` |
| Production with monitoring | `gunicorn -k UvicornWorker` |
| Kubernetes / Container Apps | Single process per container, scale horizontally |
| Azure Functions | Single process (`lifespan="off"` or `"auto"`) |

---

## Worker Process — Uvicorn inside Gunicorn {#gunicorn-workers}

From `uvicorn/workers.py`, the `UvicornWorker`:

```python
# uvicorn/workers.py (simplified)
class UvicornWorker(Worker):
    CONFIG_KWARGS = {"loop": "auto", "http": "auto"}

    def init_process(self):
        super().init_process()

    async def _serve(self):
        config = Config(
            app=self.wsgi,
            host=None,
            port=None,
            fd=self.socket.fileno(),
            lifespan="on",
            **self.CONFIG_KWARGS,
        )
        server = Server(config=config)
        await server.serve(sockets=[self.sockets[0]])
```

Key insight: Each Gunicorn worker spawns its own Uvicorn server on the **same socket** (passed via file descriptor). This is how multiple workers share the same port.

### UvicornH11Worker vs UvicornWorker

```python
# gunicorn.conf.py
# Default: uses httptools + uvloop if available
worker_class = "uvicorn.workers.UvicornWorker"

# Force h11 (pure Python, no C deps needed)
worker_class = "uvicorn.workers.UvicornH11Worker"
```
