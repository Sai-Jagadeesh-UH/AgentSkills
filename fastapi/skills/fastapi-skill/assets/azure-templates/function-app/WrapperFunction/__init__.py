# WrapperFunction/__init__.py
# This module exports the FastAPI app that function_app.py wraps.
# Your actual FastAPI app lives here (or is imported from app/).
#
# For simple projects: define the app here
# For larger projects: import from app/ subpackage

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for Azure Functions.

    Keep startup lightweight to minimize cold start latency.
    Heavy resources (DB pools) should be lazy-initialized.
    """
    logger.info("Function App starting")
    yield
    logger.info("Function App shutting down")


# Import settings lazily to avoid import-time errors
def _get_settings():
    from app.config import get_settings
    return get_settings()


settings = _get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    # Disable Swagger in production for security
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.api.router import api_router  # noqa: E402
app.include_router(api_router)

# Example endpoint (remove in production)
@app.get("/sample")
async def sample():
    return {"info": "FastAPI on Azure Functions is working!"}
