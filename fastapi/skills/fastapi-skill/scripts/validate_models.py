#!/usr/bin/env python3
"""
Pydantic Model Validator
Scans Python files for Pydantic models and reports common issues.

Usage:
    python skills/fastapi-skill/scripts/validate_models.py app/schemas/
    python skills/fastapi-skill/scripts/validate_models.py app/schemas/user.py
"""

import sys
import ast
import importlib.util
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelIssue:
    severity: str  # CRITICAL | WARNING | INFO
    model: str
    field: Optional[str]
    message: str
    suggestion: str


def find_pydantic_models(tree: ast.AST) -> list[ast.ClassDef]:
    """Find all classes that inherit from BaseModel or similar."""
    pydantic_bases = {"BaseModel", "SQLModel", "AppBaseModel"}
    models = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in pydantic_bases:
                    models.append(node)
                    break
    return models


def check_mutable_defaults(model: ast.ClassDef) -> list[ModelIssue]:
    """Check for mutable default values (list, dict, set)."""
    issues = []
    for stmt in model.body:
        if isinstance(stmt, ast.AnnAssign) and stmt.value:
            # Check for direct list/dict/set literals as defaults
            if isinstance(stmt.value, (ast.List, ast.Dict, ast.Set)):
                field_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "?"
                issues.append(ModelIssue(
                    severity="CRITICAL",
                    model=model.name,
                    field=field_name,
                    message=f"Mutable default value for field '{field_name}'",
                    suggestion=f"Use Field(default_factory=list) or Field(default_factory=dict) instead",
                ))
    return issues


def check_missing_field_descriptions(model: ast.ClassDef) -> list[ModelIssue]:
    """Check if fields have descriptions (important for OpenAPI docs)."""
    issues = []
    # Only flag on models that look like API schemas (not internal models)
    model_name = model.name
    if not any(suffix in model_name for suffix in ["Read", "Create", "Update", "Response", "Request"]):
        return []

    for stmt in model.body:
        if isinstance(stmt, ast.AnnAssign):
            field_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "?"
            if field_name.startswith("_"):
                continue

            # Check if Field() with description is used
            has_description = False
            if stmt.value:
                # Look for Field(..., description=...) call
                for node in ast.walk(stmt.value):
                    if isinstance(node, ast.keyword) and node.arg == "description":
                        has_description = True
                        break

            if not has_description:
                issues.append(ModelIssue(
                    severity="INFO",
                    model=model_name,
                    field=field_name,
                    message=f"Field '{field_name}' has no description",
                    suggestion=f"Add description='{field_name} description here' to Field() for better OpenAPI docs",
                ))
    return issues


def check_password_in_response(model: ast.ClassDef) -> list[ModelIssue]:
    """Check for password-like fields in response models."""
    issues = []
    model_name = model.name

    if not any(suffix in model_name for suffix in ["Read", "Response", "Out"]):
        return []

    sensitive_field_names = {"password", "hashed_password", "secret", "token", "api_key", "private_key"}

    for stmt in model.body:
        if isinstance(stmt, ast.AnnAssign):
            field_name = stmt.target.id if isinstance(stmt.target, ast.Name) else ""
            if field_name.lower() in sensitive_field_names:
                issues.append(ModelIssue(
                    severity="CRITICAL",
                    model=model_name,
                    field=field_name,
                    message=f"Sensitive field '{field_name}' found in response model — this will be leaked to clients!",
                    suggestion=f"Remove '{field_name}' from {model_name} or use a separate internal model",
                ))
    return issues


def check_orm_mode(model: ast.ClassDef) -> list[ModelIssue]:
    """Check if models that need ORM integration have from_attributes=True."""
    issues = []
    model_name = model.name

    if not any(suffix in model_name for suffix in ["Read", "Response", "DB"]):
        return []

    # Check if from_attributes=True is set somewhere in the class
    has_orm_mode = False
    for stmt in model.body:
        # Check for model_config = ConfigDict(from_attributes=True)
        if isinstance(stmt, ast.Assign):
            for node in ast.walk(stmt):
                if isinstance(node, ast.keyword):
                    if node.arg == "from_attributes":
                        has_orm_mode = True
                        break

    if not has_orm_mode:
        issues.append(ModelIssue(
            severity="WARNING",
            model=model_name,
            field=None,
            message=f"Response model {model_name} may need 'from_attributes=True' for ORM compatibility",
            suggestion="Add: model_config = ConfigDict(from_attributes=True) or inherit from AppBaseModel",
        ))
    return issues


def check_annotated_pattern(model: ast.ClassDef) -> list[ModelIssue]:
    """Check if old-style Field is used instead of Annotated pattern."""
    issues = []

    for stmt in model.body:
        if isinstance(stmt, ast.AnnAssign) and stmt.value:
            field_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "?"

            # Check if annotation is simple (not Annotated) but has Field with constraints
            is_annotated = False
            if isinstance(stmt.annotation, ast.Subscript):
                if isinstance(stmt.annotation.value, ast.Name):
                    is_annotated = stmt.annotation.value.id == "Annotated"

            has_field_constraints = False
            if stmt.value and not is_annotated:
                for node in ast.walk(stmt.value):
                    if isinstance(node, ast.keyword):
                        if node.arg in ("gt", "ge", "lt", "le", "min_length", "max_length", "pattern"):
                            has_field_constraints = True
                            break

            if has_field_constraints and not is_annotated:
                issues.append(ModelIssue(
                    severity="INFO",
                    model=model.name,
                    field=field_name,
                    message=f"Consider using Annotated[type, Field(...)] pattern for field '{field_name}'",
                    suggestion=f"Change to: {field_name}: Annotated[type, Field(constraint...)] for better type safety",
                ))

    return issues


def analyze_file(file_path: Path) -> list[ModelIssue]:
    """Analyze a single Python file for Pydantic model issues."""
    all_issues = []

    try:
        content = file_path.read_text()
        tree = ast.parse(content)
    except (SyntaxError, IOError) as e:
        print(f"  ⚠️  Could not parse {file_path}: {e}")
        return []

    models = find_pydantic_models(tree)

    for model in models:
        checks = [
            check_mutable_defaults(model),
            check_password_in_response(model),
            check_orm_mode(model),
            check_annotated_pattern(model),
            # check_missing_field_descriptions(model),  # too noisy, enable if desired
        ]
        for check_issues in checks:
            all_issues.extend(check_issues)

    return all_issues


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_models.py <path>")
        print("  Path can be a directory or a .py file")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = list(target.rglob("*.py"))
        files = [f for f in files if "__pycache__" not in str(f)]
    else:
        print(f"Error: {target} is not a file or directory")
        sys.exit(1)

    print(f"\n🔍 Scanning {len(files)} Python files for Pydantic model issues...\n")

    all_issues: list[tuple[Path, ModelIssue]] = []

    for file_path in sorted(files):
        issues = analyze_file(file_path)
        for issue in issues:
            all_issues.append((file_path, issue))

    if not all_issues:
        print("✅ No issues found!")
        return

    # Group by severity
    critical = [(f, i) for f, i in all_issues if i.severity == "CRITICAL"]
    warnings = [(f, i) for f, i in all_issues if i.severity == "WARNING"]
    infos = [(f, i) for f, i in all_issues if i.severity == "INFO"]

    for label, color, issues in [
        ("CRITICAL", "🔴", critical),
        ("WARNING", "🟡", warnings),
        ("INFO", "🔵", infos),
    ]:
        if issues:
            print(f"{color} {label} ({len(issues)} issue{'s' if len(issues) > 1 else ''})")
            for file_path, issue in issues:
                field_str = f".{issue.field}" if issue.field else ""
                print(f"  [{file_path.name}] {issue.model}{field_str}")
                print(f"    ⚠️  {issue.message}")
                print(f"    💡 {issue.suggestion}")
                print()

    print(f"\nSummary: {len(critical)} critical, {len(warnings)} warnings, {len(infos)} info")

    if critical:
        sys.exit(1)  # Exit with error if critical issues found


if __name__ == "__main__":
    main()
