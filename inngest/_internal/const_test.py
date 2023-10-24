import toml

from .const import VERSION


def test_version_matches_pyproject() -> None:
    """
    Ensure that the version in pyproject.toml matches the version in code.
    """

    with open("pyproject.toml", encoding="utf-8") as f:
        pyproject: dict[str, object] = toml.load(f)
        project = pyproject.get("project")
        assert isinstance(project, dict)
        assert VERSION == project.get("version")
