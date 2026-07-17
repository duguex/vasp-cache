"""HTTP API and static route tests for the read-only dashboard server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from vasp_cache import put
from vasp_cache.paths import _reset_project
from vasp_cache.web_server import create_server
from conftest import write_complete_calc


@pytest.fixture
def server_url(cache_root: Path):
    server = create_server(cache_root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def request_json(url: str, method: str = "GET") -> dict:
    request = Request(url, method=method)
    with urlopen(request) as response:
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
        assert response.headers["Cache-Control"] == "no-store"
        return json.loads(response.read())


def request_status(url: str, method: str = "GET") -> int:
    try:
        with urlopen(Request(url, method=method)) as response:
            return response.status
    except HTTPError as error:
        return error.code


def test_overview_api_returns_sqlite_only_payload(
    cache_root: Path, tmp_path: Path, server_url: str
):
    _reset_project()
    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    response = request_json(server_url + "/api/overview?top_formulas=5")
    assert response["entries"] == 1
    assert response["storage_scan"] is False


def test_entries_api_filters_and_paginates(
    cache_root: Path, tmp_path: Path, server_url: str
):
    _reset_project()
    put(write_complete_calc(tmp_path / "first"), provenance="canonical")
    second = write_complete_calc(tmp_path / "second", energy="-4.0")
    (second / "INCAR").write_text((second / "INCAR").read_text() + "\nENCUT=400\n")
    put(second, provenance="sampled")
    response = request_json(
        server_url + "/api/entries?provenance=all&limit=1&offset=1"
    )
    assert len(response["rows"]) == 1
    assert response["limit"] == 1
    assert response["offset"] == 1
    assert isinstance(response["has_more"], bool)


def test_entry_api_returns_detail_and_missing_hash_is_404(
    cache_root: Path, tmp_path: Path, server_url: str
):
    _reset_project()
    content_hash = put(write_complete_calc(tmp_path / "calc"))
    detail = request_json(server_url + "/api/entry/" + quote(content_hash))
    assert detail["content_hash"] == content_hash
    assert "OUTCAR" in detail["objects"]
    assert request_status(server_url + "/api/entry/missing") == 404


def test_objects_api_supports_strict_boolean(
    cache_root: Path, server_url: str
):
    response = request_json(server_url + "/api/objects?orphans_only=1")
    assert response["orphans_only"] is True
    assert response["rows"] == []


def test_invalid_query_values_return_json_400(cache_root: Path, server_url: str):
    for query in (
        "top_formulas=bad",
        "limit=bad",
        "bandgap_min=bad",
        "converged_only=maybe",
        "orphans_only=yes",
        "provenance=invalid",
    ):
        with pytest.raises(HTTPError) as caught:
            request_json(server_url + "/api/entries?" + query)
        assert caught.value.code == 400
        payload = json.loads(caught.value.read())
        assert "error" in payload
        assert caught.value.headers["Content-Type"] == "application/json; charset=utf-8"


def test_unsupported_method_and_route_are_rejected(cache_root: Path, server_url: str):
    assert request_status(server_url + "/missing") == 404
    assert request_status(server_url + "/api/overview", method="POST") == 405
    assert request_status(server_url + "/api/overview", method="HEAD") == 405


def test_missing_cache_root_is_not_created(tmp_path: Path):
    root = tmp_path / "missing-cache"
    server = create_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        assert request_status(f"http://{host}:{port}/api/overview") == 200
        assert not root.exists()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_arbitrary_files_are_never_served(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()
    server = create_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        assert request_status(f"http://{host}:{port}/etc/passwd") == 404
        assert request_status(f"http://{host}:{port}/../etc/passwd") == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_static_routes_are_fixed_and_missing_assets_are_404(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()
    server = create_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        assert request_status(f"http://{host}:{port}/not-an-asset") == 404
        assert request_status(f"http://{host}:{port}/app.js/extra") == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
