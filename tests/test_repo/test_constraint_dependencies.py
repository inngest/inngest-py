from __future__ import annotations

from pathlib import Path

import pydantic
import toml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

workspace_deps = [
    "inngest",
    "test_core",
    "inngest_encryption",
    "inngest_langchain",
]


def test_constraint_dependencies_match_minimum_versions() -> None:
    """
    Verify that constraint-dependencies array versions match the minimum
    versions in workspace pyproject.toml files. This ensures that CI runs using
    the minimum versions of dependencies that we claim to support
    """

    root_path = Path(__file__).parent.parent.parent
    with open(root_path / "pyproject.toml") as f:
        root_config = RootConfig.model_validate(toml.load(f))

    constraints = _get_constraint_dependencies(root_config)

    dep_mins: dict[str, str] = {}
    for member in root_config.tool.uv.workspace.members:
        # Load workspace pyproject.toml
        with open(root_path / member / "pyproject.toml") as f:
            workspace_config = WorkspaceConfig.model_validate(toml.load(f))

        deps = list(workspace_config.project.dependencies)
        for (
            group_deps
        ) in workspace_config.project.optional_dependencies.values():
            deps.extend(group_deps)

        for dep in deps:
            name, min_version = _parse_min_version(dep, member)
            if name is None:
                continue

            existing_min = dep_mins.get(name)
            if existing_min:
                dep_mins[name] = _use_min_version(existing_min, min_version)
            else:
                dep_mins[name] = min_version

    # Ensure constraint versions match minimum versions in workspaces
    for dep_name, min_version in dep_mins.items():
        assert dep_name in constraints, (
            f"Dependency '{dep_name}' is not in constraint-dependencies"
        )

        assert min_version == constraints[dep_name], (
            f"Dependency '{dep_name}' has minimum version '{min_version}' but constraint-dependencies specifies '{constraints[dep_name]}'"
        )

    # Ensure all constraints match real dependencies in workspaces
    for dep_name in constraints:
        assert dep_name in dep_mins, (
            f"Dependency '{dep_name}' is in constraint-dependencies but has no corresponding minimum version in workspace pyproject.toml files"
        )


class RootConfig(pydantic.BaseModel):
    tool: RootConfigTool


class RootConfigTool(pydantic.BaseModel):
    uv: RootConfigToolUvConfig


class RootConfigToolUvConfig(pydantic.BaseModel):
    constraint_dependencies: list[str] = pydantic.Field(
        alias="constraint-dependencies"
    )
    workspace: RootConfigToolUvWorkspaceConfig


class RootConfigToolUvWorkspaceConfig(pydantic.BaseModel):
    members: list[str]


class WorkspaceConfig(pydantic.BaseModel):
    project: WorkspaceConfigProject


class WorkspaceConfigProject(pydantic.BaseModel):
    dependencies: list[str]
    optional_dependencies: dict[str, list[str]] = pydantic.Field(
        alias="optional-dependencies",
        default_factory=dict,
    )


def _get_constraint_dependencies(
    root_config: RootConfig,
) -> dict[str, str]:
    """
    Get the constraint dependencies from the root pyproject.toml
    """

    constraints: dict[str, str] = {}
    for dep in root_config.tool.uv.constraint_dependencies:
        assert "==" in dep, f"Invalid constraint format: {dep}"
        parts = dep.split("==")
        assert len(parts) == 2, f"Invalid constraint format: {dep}"
        package, version = parts
        constraints[canonicalize_name(package)] = version
    return constraints


def _parse_min_version(dep: str, member: str) -> tuple[str | None, str]:
    """
    Name and ">=" version of a dependency. The name is None for workspace
    dependencies, whose versions come from the workspace
    """

    req = Requirement(dep)
    if req.name in workspace_deps:
        return None, ""

    mins = [s.version for s in req.specifier if s.operator == ">="]
    assert len(mins) == 1, (
        f"Dependency '{dep}' in {member} needs exactly one '>=' constraint"
    )
    return canonicalize_name(req.name), mins[0]


def _use_min_version(a: str, b: str) -> str:
    """
    Compare two version strings and return the minimum version
    """

    a_parts = tuple(map(int, a.split(".")))
    b_parts = tuple(map(int, b.split(".")))

    if a_parts < b_parts:
        return a
    elif a_parts > b_parts:
        return b
    return a
