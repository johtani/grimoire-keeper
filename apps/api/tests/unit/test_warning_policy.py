"""Regression tests for the repository-wide warning policy."""

import tomllib
import warnings
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "category",
    [DeprecationWarning, RuntimeWarning, ResourceWarning, UserWarning],
)
def test_unknown_warnings_are_errors(category: type[Warning]) -> None:
    """Project and dependency regressions must fail the normal test run."""
    with pytest.raises(category, match="warning policy probe"):
        warnings.warn("warning policy probe", category, stacklevel=1)


def test_pytest_configuration_has_no_blanket_warning_suppression() -> None:
    """Keep warning enforcement in the shared pytest configuration."""
    repository_root = Path(__file__).resolve().parents[4]
    with (repository_root / "pyproject.toml").open("rb") as pyproject_file:
        pytest_config = tomllib.load(pyproject_file)["tool"]["pytest"]["ini_options"]

    assert pytest_config["filterwarnings"] == ["error"]
    assert "--disable-warnings" not in pytest_config["addopts"]
    assert not any(
        value.startswith("PYTHONWARNINGS=") for value in pytest_config["env"]
    )
