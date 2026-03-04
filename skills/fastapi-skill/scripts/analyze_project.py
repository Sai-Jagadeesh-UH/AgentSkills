#!/usr/bin/env python3
"""
FastAPI Project Analyzer
Scans an existing project and produces a structured report for the fastapi-skill.

Usage:
    python skills/fastapi-skill/scripts/analyze_project.py .
    python skills/fastapi-skill/scripts/analyze_project.py /path/to/project
"""

import sys
import os
import json
import ast
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class FileIssue:
    severity: str  # CRITICAL | WARNING | INFO
    file: str
    line: Optional[int]
    message: str


@dataclass
class ProjectReport:
    project_root: str
    python_version: Optional[str] = None
    package_manager: Optional[str] = None
    framework: Optional[str] = None
    framework_version: Optional[str] = None

    # Dependencies detected
    has_fastapi: bool = False
    has_pydantic: bool = False
    has_sqlalchemy: bool = False
    has_asyncpg: bool = False
    has_alembic: bool = False
    has_redis: bool = False
    has_celery: bool = False
    has_arq: bool = False
    has_jwt: bool = False
    has_httpx: bool = False
    has_uvicorn: bool = False
    has_gunicorn: bool = False
    has_nicegui: bool = False
    has_jinja2: bool = False

    # Deployment
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_azure_config: bool = False
    has_azure_functions: bool = False
    has_github_actions: bool = False
    has_env_example: bool = False
    has_health_endpoint: bool = False

    # Structure
    structure: dict = field(default_factory=dict)
    missing_dirs: list = field(default_factory=list)
    existing_dirs: list = field(default_factory=list)

    # API analysis
    routers_found: list = field(default_factory=list)
    endpoints_found: list = field(default_factory=list)
    has_versioning: bool = False
    has_lifespan: bool = False
    has_response_models: bool = False
    has_auth_dependencies: bool = False

    # Issues
    issues: list = field(default_factory=list)

    # Recommendations
    top_actions: list = field(default_factory=list)


def detect_package_manager(root: Path) -> tuple[str, dict]:
    """Returns (package_manager_name, dependencies_dict)"""
    deps = {}

    if (root / "uv.lock").exists():
        pm = "uv"
        if (root / "pyproject.toml").exists():
            deps = parse_pyproject_deps(root / "pyproject.toml")
    elif (root / "pyproject.toml").exists():
        pm = "poetry" if (root / "poetry.lock").exists() else "pip/pyproject"
        deps = parse_pyproject_deps(root / "pyproject.toml")
    elif (root / "Pipfile").exists():
        pm = "pipenv"
        deps = parse_pipfile_deps(root / "Pipfile")
    elif (root / "requirements.txt").exists():
        pm = "pip"
        deps = parse_requirements(root / "requirements.txt")
    else:
        pm = "unknown"

    return pm, deps


def parse_requirements(path: Path) -> dict:
    deps = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Split on version specifiers
                for sep in ["==", ">=", "<=", "~=", "!=", ">"]:
                    if sep in line:
                        name, version = line.split(sep, 1)
                        deps[name.strip().lower().replace("-", "_")] = version.strip()
                        break
                else:
                    deps[line.lower().replace("-", "_")] = "any"
    except Exception:
        pass
    return deps


def parse_pyproject_deps(path: Path) -> dict:
    deps = {}
    try:
        content = path.read_text()
        # Simple extraction - look for dependencies section
        in_deps = False
        for line in content.splitlines():
            if "[project.dependencies]" in line or '"dependencies"' in line:
                in_deps = True
            elif in_deps and line.startswith("["):
                in_deps = False
            elif in_deps and "=" in line:
                parts = line.split("=", 1)
                name = parts[0].strip().strip('"').lower().replace("-", "_")
                deps[name] = parts[1].strip().strip('"')
            # Also check simple list format
            elif in_deps and line.strip().startswith('"'):
                name = line.strip().strip('"').split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip()
                deps[name.lower().replace("-", "_")] = "any"
    except Exception:
        pass
    return deps


def parse_pipfile_deps(path: Path) -> dict:
    return parse_pyproject_deps(path)  # similar format


def check_python_files_for_issues(py_files: list[Path], report: ProjectReport):
    """Scan Python files for common anti-patterns."""

    blocking_imports = ["requests", "time.sleep", "subprocess.run"]
    orm_in_response_patterns = ["return db_"]

    for py_file in py_files:
        try:
            content = py_file.read_text()
            lines = content.splitlines()

            # Check for blocking calls in async functions
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.AsyncFunctionDef,)):
                        for child in ast.walk(node):
                            if isinstance(child, ast.Call):
                                # Check for time.sleep
                                if isinstance(child.func, ast.Attribute):
                                    if (hasattr(child.func, 'attr') and
                                            child.func.attr == 'sleep' and
                                            isinstance(child.func.value, ast.Name) and
                                            child.func.value.id == 'time'):
                                        report.issues.append(FileIssue(
                                            severity="WARNING",
                                            file=str(py_file),
                                            line=getattr(child, 'lineno', None),
                                            message="time.sleep() in async function blocks event loop. Use await asyncio.sleep()"
                                        ))
            except SyntaxError:
                pass

            # Check for requests in async context (heuristic)
            for i, line in enumerate(lines, 1):
                if "requests.get(" in line or "requests.post(" in line:
                    # Check if inside async function (rough heuristic)
                    report.issues.append(FileIssue(
                        severity="WARNING",
                        file=str(py_file),
                        line=i,
                        message="Blocking requests library detected. Use httpx.AsyncClient for async endpoints"
                    ))

            # Check for deprecated on_event
            if "@app.on_event" in content or "on_event(" in content:
                report.issues.append(FileIssue(
                    severity="INFO",
                    file=str(py_file),
                    line=None,
                    message="Deprecated @app.on_event used. Migrate to lifespan context manager"
                ))

            # Check for response_model usage
            if "@app.get" in content or "@router.get" in content:
                if "response_model" not in content:
                    report.issues.append(FileIssue(
                        severity="WARNING",
                        file=str(py_file),
                        line=None,
                        message="Endpoints without response_model may leak sensitive fields"
                    ))

            # Check for FastAPI app and lifespan
            if "FastAPI(" in content:
                if "lifespan" in content:
                    report.has_lifespan = True

            # Check for auth dependencies
            if "Depends(get_current_user" in content or "OAuth2" in content:
                report.has_auth_dependencies = True

            # Check for versioning
            if "/v1/" in content or 'prefix="/v1"' in content:
                report.has_versioning = True

            # Find routers
            if "APIRouter" in content:
                report.routers_found.append(str(py_file))

            # Check health endpoint
            if '"/health"' in content or "'/health'" in content:
                report.has_health_endpoint = True

        except Exception:
            continue


def analyze_structure(root: Path, report: ProjectReport):
    """Check for standard FastAPI directory structure."""

    expected_dirs = [
        ("app", "Main application package"),
        ("app/api", "API routers"),
        ("app/api/v1", "Versioned API routers"),
        ("app/core", "Core utilities (security, config)"),
        ("app/models", "ORM models"),
        ("app/schemas", "Pydantic schemas"),
        ("app/services", "Business logic layer"),
        ("app/repositories", "Data access layer"),
        ("tests", "Test suite"),
        ("tests/test_api", "API endpoint tests"),
        ("alembic", "Database migrations"),
    ]

    expected_files = [
        ("app/main.py", "FastAPI app factory"),
        ("app/config.py", "Settings via pydantic-settings"),
        ("app/dependencies.py", "Shared FastAPI dependencies"),
        ("Dockerfile", "Container image"),
        ("docker-compose.yml", "Local development compose"),
        (".env.example", "Environment variable template"),
        ("pyproject.toml", "Project metadata and dependencies"),
        ("tests/conftest.py", "Test fixtures"),
    ]

    structure = {}
    for dir_path, description in expected_dirs:
        full_path = root / dir_path
        exists = full_path.is_dir()
        structure[dir_path] = {"exists": exists, "type": "dir", "description": description}
        if exists:
            report.existing_dirs.append(dir_path)
        else:
            report.missing_dirs.append(dir_path)

    for file_path, description in expected_files:
        full_path = root / file_path
        exists = full_path.is_file()
        structure[file_path] = {"exists": exists, "type": "file", "description": description}

    report.structure = structure


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_project.py <project_root>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory")
        sys.exit(1)

    report = ProjectReport(project_root=str(root))

    # 1. Detect package manager and dependencies
    pm, deps = detect_package_manager(root)
    report.package_manager = pm

    # 2. Check dependencies
    report.has_fastapi = any("fastapi" in k for k in deps)
    report.has_pydantic = any("pydantic" in k for k in deps)
    report.has_sqlalchemy = any("sqlalchemy" in k for k in deps)
    report.has_asyncpg = any("asyncpg" in k for k in deps)
    report.has_alembic = any("alembic" in k for k in deps)
    report.has_redis = any("redis" in k for k in deps)
    report.has_celery = any("celery" in k for k in deps)
    report.has_arq = any("arq" in k for k in deps)
    report.has_jwt = any("jwt" in k or "jose" in k for k in deps)
    report.has_httpx = any("httpx" in k for k in deps)
    report.has_uvicorn = any("uvicorn" in k for k in deps)
    report.has_gunicorn = any("gunicorn" in k for k in deps)
    report.has_nicegui = any("nicegui" in k for k in deps)
    report.has_jinja2 = any("jinja2" in k or "jinja" in k for k in deps)

    # 3. Check deployment files
    report.has_dockerfile = (root / "Dockerfile").is_file()
    report.has_docker_compose = (
        (root / "docker-compose.yml").is_file() or
        (root / "docker-compose.yaml").is_file()
    )
    report.has_azure_config = (
        (root / ".azure").is_dir() or
        (root / "azure.yaml").is_file() or
        (root / "host.json").is_file()
    )
    report.has_azure_functions = (root / "host.json").is_file()
    report.has_github_actions = (root / ".github" / "workflows").is_dir()
    report.has_env_example = (
        (root / ".env.example").is_file() or
        (root / ".env.sample").is_file()
    )

    # 4. Detect Python version
    python_version_file = root / ".python-version"
    if python_version_file.is_file():
        report.python_version = python_version_file.read_text().strip()

    # 5. Analyze structure
    analyze_structure(root, report)

    # 6. Scan Python files
    py_files = list(root.rglob("*.py"))
    # Exclude venv, .venv, node_modules, __pycache__
    py_files = [
        f for f in py_files
        if not any(part in f.parts for part in [".venv", "venv", "__pycache__", "node_modules", ".git"])
    ]
    check_python_files_for_issues(py_files, report)

    # 7. Generate recommendations
    actions = []

    if not report.has_fastapi:
        actions.append("CRITICAL: FastAPI not found in dependencies. Run: pip install 'fastapi[standard]'")

    if "app/schemas" in report.missing_dirs and report.has_fastapi:
        actions.append("CRITICAL: Create app/schemas/ directory and separate Pydantic schemas from ORM models")

    if not report.has_auth_dependencies and report.has_fastapi:
        actions.append("HIGH: No authentication found. Implement JWT or API key auth via dependencies.py")

    if not report.has_health_endpoint:
        actions.append("MEDIUM: Add /health and /ready endpoints for deployment health checks")

    if not report.has_dockerfile:
        actions.append("MEDIUM: Create Dockerfile for containerization")

    if not report.has_env_example:
        actions.append("LOW: Create .env.example to document required environment variables")

    if not report.has_lifespan and report.has_fastapi:
        actions.append("LOW: Migrate to lifespan context manager (replaces deprecated @app.on_event)")

    if not report.has_versioning and report.has_fastapi:
        actions.append("LOW: Consider adding API versioning (/api/v1/) for future-proofing")

    report.top_actions = actions[:8]

    # 8. Output report
    print("\n" + "="*60)
    print("FASTAPI PROJECT ANALYSIS REPORT")
    print("="*60)
    print(f"\nProject: {report.project_root}")
    print(f"Package Manager: {report.package_manager}")
    print(f"Python Version: {report.python_version or 'not detected'}")

    print("\n--- DEPENDENCIES ---")
    dep_status = [
        ("FastAPI", report.has_fastapi),
        ("Pydantic", report.has_pydantic),
        ("SQLAlchemy", report.has_sqlalchemy),
        ("asyncpg", report.has_asyncpg),
        ("Alembic", report.has_alembic),
        ("Redis", report.has_redis),
        ("Celery/ARQ", report.has_celery or report.has_arq),
        ("JWT", report.has_jwt),
        ("httpx", report.has_httpx),
        ("Uvicorn", report.has_uvicorn),
        ("NiceGUI", report.has_nicegui),
        ("Jinja2", report.has_jinja2),
    ]
    for name, present in dep_status:
        print(f"  {'✅' if present else '❌'} {name}")

    print("\n--- DEPLOYMENT ---")
    deploy_status = [
        ("Dockerfile", report.has_dockerfile),
        ("docker-compose.yml", report.has_docker_compose),
        ("Azure Functions (host.json)", report.has_azure_functions),
        ("Azure config (.azure/)", report.has_azure_config),
        ("GitHub Actions", report.has_github_actions),
        (".env.example", report.has_env_example),
    ]
    for name, present in deploy_status:
        print(f"  {'✅' if present else '❌'} {name}")

    print("\n--- PROJECT STRUCTURE ---")
    for path, info in report.structure.items():
        marker = "✅" if info["exists"] else "❌"
        print(f"  {marker} {path:<35} ({info['description']})")

    print("\n--- API ANALYSIS ---")
    print(f"  Routers found: {len(report.routers_found)}")
    for r in report.routers_found:
        print(f"    • {r}")
    print(f"  API Versioning: {'✅' if report.has_versioning else '❌'}")
    print(f"  Lifespan context: {'✅' if report.has_lifespan else '❌'}")
    print(f"  Auth dependencies: {'✅' if report.has_auth_dependencies else '❌'}")
    print(f"  Health endpoint: {'✅' if report.has_health_endpoint else '❌'}")

    if report.issues:
        print(f"\n--- ISSUES FOUND ({len(report.issues)}) ---")
        for issue in report.issues[:20]:  # limit output
            line_str = f":{issue.line}" if issue.line else ""
            print(f"  [{issue.severity}] {issue.file}{line_str}")
            print(f"    → {issue.message}")

    print("\n--- TOP RECOMMENDATIONS ---")
    for i, action in enumerate(report.top_actions, 1):
        print(f"  {i}. {action}")

    print("\n" + "="*60)

    # Also output JSON for programmatic use
    report_file = Path(report.project_root) / ".fastapi-skill-analysis.json"
    try:
        report_dict = asdict(report)
        report_dict["issues"] = [asdict(i) for i in report.issues]
        with open(report_file, "w") as f:
            json.dump(report_dict, f, indent=2)
        print(f"\nFull report saved to: {report_file}")
    except Exception as e:
        print(f"\nNote: Could not save JSON report: {e}")

    return report


if __name__ == "__main__":
    main()
