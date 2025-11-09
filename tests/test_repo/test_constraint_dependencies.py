import re
from pathlib import Path

import toml

workspace_deps = ["inngest", "test_core", "inngest_encryption"]


def test_constraint_dependencies_match_minimum_versions() -> None:
    """
    Verify that constraint-dependencies array versions match the minimum
    versions in workspace pyproject.toml files. This ensures that CI runs using
    the minimum versions of dependencies that we claim to support
    """

    root_path = Path(__file__).parent.parent.parent
    with open(root_path / "pyproject.toml") as f:
        root_config = toml.load(f)

    constraints = get_constraint_dependencies(root_config)

    dep_mins: dict[str, str] = {}
    for member in get_workspace_members(root_config):
        # Load workspace pyproject.toml
        with open(root_path / member / "pyproject.toml") as f:
            workspace_config = toml.load(f)

        project_config = workspace_config.get("project")
        assert isinstance(project_config, dict)

        # Parse dependencies
        dependencies_config = project_config.get("dependencies")
        assert isinstance(dependencies_config, list)
        for dep_name in dependencies_config:
            assert isinstance(dep_name, str)

            if dep_name in workspace_deps:
                continue

            assert ">=" in dep_name, (
                f"Dependency '{dep_name}' in {member} has no version constraint"
            )

            parts = dep_name.split(">=")
            assert len(parts) == 2
            existing_min = dep_mins.get(parts[0])
            if existing_min:
                dep_mins[parts[0]] = use_min_version(existing_min, parts[1])
            else:
                dep_mins[parts[0]] = parts[1]

        # Parse optional dependencies
        optional_dependencies_config = project_config.get(
            "optional-dependencies",
            {},
        )
        assert isinstance(optional_dependencies_config, dict)
        for _, group_deps in optional_dependencies_config.items():
            assert isinstance(group_deps, list)
            for dep_name in group_deps:
                assert isinstance(dep_name, str)

                if dep_name in workspace_deps:
                    continue

                assert ">=" in dep_name, (
                    f"Dependency '{dep_name}' in {member} has no version constraint"
                )

                parts = dep_name.split(">=")
                assert len(parts) == 2
                existing_min = dep_mins.get(parts[0])
                if existing_min:
                    dep_mins[parts[0]] = use_min_version(existing_min, parts[1])
                else:
                    dep_mins[parts[0]] = parts[1]

    # Ensure constraint versions match minimum versions in workspaces
    for dep_name, min_version in dep_mins.items():
        assert dep_name in constraints, (
            f"Dependency '{dep_name}' is not in constraint-dependencies"
        )

        assert min_version == constraints[dep_name], (
            f"Dependency '{dep_name}' has minimum version '{min_version}' in {member} but constraint-dependencies specifies '{constraints[dep_name]}'"
        )

    # Ensure all constraints match real dependencies in workspaces
    for dep_name in constraints:
        assert dep_name in dep_mins, (
            f"Dependency '{dep_name}' is in constraint-dependencies but has no corresponding minimum version in workspace pyproject.toml files"
        )


def get_constraint_dependencies(
    root_config: dict[str, object],
) -> dict[str, str]:
    """
    Get the constraint dependencies from the root pyproject.toml
    """

    tool_config = root_config.get("tool")
    assert isinstance(tool_config, dict)
    uv_config = tool_config.get("uv")
    assert isinstance(uv_config, dict)
    constraint_deps = uv_config.get("constraint-dependencies")
    assert isinstance(constraint_deps, list)

    constraints: dict[str, str] = {}
    for dep in constraint_deps:
        match = re.match(r"^([a-zA-Z0-9_-]+)==(.+)$", dep)
        assert match, f"Invalid constraint format: {dep}"
        package, version = match.groups()
        assert isinstance(package, str)
        assert isinstance(version, str)
        constraints[package] = version
    return constraints


def get_workspace_members(root_config: dict[str, object]) -> list[str]:
    """
    Get the list of workspace members from the root pyproject.toml
    """

    tool_config = root_config.get("tool")
    assert isinstance(tool_config, dict)
    uv_config = tool_config.get("uv")
    assert isinstance(uv_config, dict)
    workspace_config = uv_config.get("workspace")
    assert isinstance(workspace_config, dict)
    members = workspace_config.get("members")
    assert isinstance(members, list)
    return members


def use_min_version(a: str, b: str) -> str:
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
