from __future__ import annotations

from pathlib import Path

import pytest

from vasp_cache.paths import cache_root, override_cache_root


def test_cache_root_override(tmp_path: Path) -> None:
    from vasp_cache import paths

    paths._reset_project()
    other = tmp_path / "other"
    other.mkdir()
    override_cache_root(other)
    assert cache_root() == other.resolve()


def test_cache_root_default_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from vasp_cache import paths

    paths._reset_project()
    monkeypatch.delenv("VASP_CACHE_ROOT", raising=False)
    got = cache_root()
    assert got == Path("/mnt/shared/vasp_cache")


def test_cache_root_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from vasp_cache import paths

    paths._reset_project()
    monkeypatch.setenv("VASP_CACHE_ROOT", "/some/custom/path")
    got = cache_root()
    assert got == Path("/some/custom/path").resolve()


def test_override_cache_root_none_resets_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from vasp_cache import paths

    paths._reset_project()
    monkeypatch.setenv("VASP_CACHE_ROOT", "/env/path")
    override_cache_root(None)
    got = cache_root()
    assert got == Path("/env/path").resolve()
