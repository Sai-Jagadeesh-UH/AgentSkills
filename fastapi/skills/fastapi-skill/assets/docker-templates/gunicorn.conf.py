# gunicorn.conf.py — Production Gunicorn configuration
import multiprocessing

# Worker configuration
workers = multiprocessing.cpu_count() * 2 + 1  # formula for I/O-bound APIs
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
threads = 1  # Uvicorn workers are single-threaded (asyncio handles concurrency)

# Binding
bind = "0.0.0.0:8000"
backlog = 2048

# Timeouts
timeout = 120            # seconds before killing a worker (increase for slow ops)
graceful_timeout = 30    # seconds to wait for workers to finish on shutdown
keepalive = 5            # seconds to keep idle connections open

# Memory management
max_requests = 1000          # restart worker after N requests (prevent memory leaks)
max_requests_jitter = 100    # randomize restart timing to avoid thundering herd

# Logging
loglevel = "info"
accesslog = "-"    # stdout
errorlog = "-"     # stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(L)ss'

# Process naming
proc_name = "fastapi-app"

# Lifecycle hooks
def on_starting(server):
    server.log.info("Gunicorn master starting")

def post_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_exit(server, worker):
    server.log.info(f"Worker exiting (pid: {worker.pid})")

def worker_abort(worker):
    worker.log.warning(f"Worker aborted (pid: {worker.pid})")
