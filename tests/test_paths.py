from __future__ import annotations

from pathlib import Path

import pytest
import signac

from vasp_cache.paths import cache_root, get_project, override_cache_root


def test_get_project_creates_signac(cache_root: Path) -> None:
    from vasp_cache import paths

    paths._reset_project()  # clear singleton
    project = get_project()
    assert Path(project.path) == cache_root
    assert (cache_root / ".signac").exists()
    assert signac.get_project(path=str(cache_root)) is not None


def test_override_cache_root(tmp_path: Path) -> None:
    from vasp_cache import paths

    paths._reset_project()
    other = tmp_path / "other"
    other.mkdir()
    override_cache_root(other)
    p = get_project()
    assert Path(p.path) == other


def test_cache_root_default_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from vasp_cache import paths

    paths._reset_project()
    monkeypatch.delenv("VASP_CACHE_ROOT", raising=False)
    # patch home so we don't wreck anything
    fake_home = Path("/tmp/fake_vasp_home")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    got = cache_root()
    assert got == fake_home / ".vasp_cache"


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
