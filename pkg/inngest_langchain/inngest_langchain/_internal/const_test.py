import toml

from . import const


def test_version_matches_pyproject() -> None:
    with open("pyproject.toml", encoding="utf-8") as f:
        project = toml.load(f)["project"]
    assert const.VERSION == project["version"], (
        "If this is local development, run `make install`"
    )
    assert const.ORIGIN == f"inngest-langchain@{project['version']}"
