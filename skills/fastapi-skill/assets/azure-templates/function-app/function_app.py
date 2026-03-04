# function_app.py — Azure Functions ASGI bridge
# Place this file at the project ROOT (not inside app/)
#
# This is the official pattern from Azure Samples:
# https://github.com/Azure-Samples/fastapi-on-azure-functions
#
# Deployment:
#   func start                                    (local dev)
#   func azure functionapp publish <func-name>    (deploy)
#   azd up                                        (full IaC deploy)

import azure.functions as func
from WrapperFunction import app as fastapi_app

# AsgiFunctionApp wraps your FastAPI app as an Azure Function
# http_auth_level controls Azure Function-level auth (separate from app-level auth):
#   ANONYMOUS  — no Azure key needed (handle auth in FastAPI middleware)
#   FUNCTION   — requires function-level key in X-Functions-Key header
#   ADMIN      — requires master key
app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS,
)
