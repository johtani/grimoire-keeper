"""Keep compromised LiteLLM releases out of dependency resolution."""

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

PROJECT_ROOT = Path(__file__).parents[4]


def litellm_requirement() -> Requirement:
    """Read the actual API requirement rather than duplicating its constraints."""
    with (PROJECT_ROOT / "apps/api/pyproject.toml").open("rb") as source:
        dependencies = tomllib.load(source)["project"]["dependencies"]
    return next(
        requirement
        for dependency in dependencies
        if (requirement := Requirement(dependency)).name == "litellm"
    )


@pytest.mark.parametrize("version", ["1.82.7", "1.82.8", "1.107.0", "1.107.1"])
def test_litellm_rejects_compromised_and_unreviewed_releases(version: str) -> None:
    """Both incidents stay blocked, including unreviewed October successors."""
    assert Version(version) not in litellm_requirement().specifier


@pytest.mark.parametrize("version", ["1.77.7", "1.82.6", "1.83.0", "1.106.2"])
def test_litellm_allows_versions_outside_the_blocked_ranges(version: str) -> None:
    """Exclusions must not unnecessarily reject other releases."""
    assert Version(version) in litellm_requirement().specifier


def test_locked_litellm_satisfies_dependency_policy() -> None:
    """The committed lockfile must agree with the API's security constraints."""
    with (PROJECT_ROOT / "uv.lock").open("rb") as source:
        packages = tomllib.load(source)["package"]
    litellm = next(package for package in packages if package["name"] == "litellm")
    assert Version(litellm["version"]) in litellm_requirement().specifier
