from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).parents[1]


def test_pyproject_packages_dashboard_assets():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_data = config["tool"]["setuptools"]["package-data"]["vasp_cache"]
    assert "web/*.html" in package_data
    assert "web/*.js" in package_data
    assert "web/*.css" in package_data
