"""Read-only HTTP API and fixed static routes for the cache dashboard."""

from __future__ import annotations

import json
import math
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from vasp_cache import inspection


_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_STATIC_ROUTES = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
_ENTRIES_FILTERS = {
    "formula",
    "functional",
    "tags",
    "bandgap_min",
    "lattice_max",
    "min_energy",
    "max_energy",
    "converged_only",
    "provenance",
    "limit",
    "offset",
}
_PROVENANCES = {"canonical", "sampled", "unknown", "all"}


class _BadRequest(ValueError):
    pass


def _single_query(query: str, allowed: set[str]) -> dict[str, str]:
    """Parse a fixed query schema and reject unknown or repeated parameters."""
    values = parse_qs(query, keep_blank_values=True, strict_parsing=False)
    unknown = set(values) - allowed
    if unknown:
        raise _BadRequest(f"unknown query parameter: {sorted(unknown)[0]}")
    result: dict[str, str] = {}
    for name, items in values.items():
        if len(items) != 1:
            raise _BadRequest(f"query parameter must appear once: {name}")
        result[name] = items[0]
    return result


def _integer(values: dict[str, str], name: str, default: int, *, minimum: int = 0) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        value = int(raw, 10)
    except (TypeError, ValueError) as exc:
        raise _BadRequest(f"invalid integer for {name}") from exc
    if value < minimum:
        raise _BadRequest(f"{name} must be at least {minimum}")
    return value


def _number(values: dict[str, str], name: str) -> float | None:
    raw = values.get(name)
    if raw is None or raw == "":
        if raw == "":
            raise _BadRequest(f"invalid number for {name}")
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise _BadRequest(f"invalid number for {name}") from exc
    if not math.isfinite(value):
        raise _BadRequest(f"invalid number for {name}")
    return value


def _boolean(values: dict[str, str], name: str, default: bool = False) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    if raw in {"true", "1"}:
        return True
    if raw in {"false", "0"}:
        return False
    raise _BadRequest(f"invalid boolean for {name}")


def _filter_text(values: dict[str, str], name: str) -> str | None:
    value = values.get(name)
    return value or None


def _handler_for(cache_root: Path) -> type[BaseHTTPRequestHandler]:
    class CacheRequestHandler(BaseHTTPRequestHandler):
        """Serve only the configured read-only API and fixed package assets."""

        server_version = "vasp-cache-web/1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler interface
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/api/overview":
                    self._overview(parsed.query)
                elif parsed.path == "/api/entries":
                    self._entries(parsed.query)
                elif parsed.path == "/api/objects":
                    self._objects(parsed.query)
                elif parsed.path.startswith("/api/entry/"):
                    self._entry(parsed.path)
                elif parsed.path in _STATIC_ROUTES:
                    self._static(parsed.path)
                else:
                    self._json_error(HTTPStatus.NOT_FOUND, "route not found")
            except _BadRequest as exc:
                self._json_error(HTTPStatus.BAD_REQUEST, str(exc))

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_PUT(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def _method_not_allowed(self) -> None:
            self._json_error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

        def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_TRACE(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()

        def do_CONNECT(self) -> None:  # noqa: N802 - stdlib handler interface
            self._method_not_allowed()
        def __getattr__(self, name: str) -> Any:
            if name.startswith("do_"):
                return self._method_not_allowed
            raise AttributeError(name)


        def _overview(self, query: str) -> None:
            values = _single_query(query, {"top_formulas"})
            top_formulas = _integer(values, "top_formulas", 10)
            self._send_json(inspection.overview(cache_root, top_formulas=top_formulas))

        def _entries(self, query: str) -> None:
            values = _single_query(query, _ENTRIES_FILTERS)
            limit = _integer(values, "limit", 50)
            offset = _integer(values, "offset", 0)
            provenance = values.get("provenance", "canonical")
            if provenance not in _PROVENANCES:
                raise _BadRequest("invalid provenance filter")
            rows = inspection.entries(
                cache_root,
                formula=_filter_text(values, "formula"),
                functional=_filter_text(values, "functional"),
                tags=_filter_text(values, "tags"),
                bandgap_min=_number(values, "bandgap_min"),
                lattice_max=_number(values, "lattice_max"),
                min_energy=_number(values, "min_energy"),
                max_energy=_number(values, "max_energy"),
                converged_only=_boolean(values, "converged_only"),
                provenance=provenance,
                limit=limit,
                offset=offset,
            )
            self._send_json(
                {
                    "rows": rows,
                    "limit": limit,
                    "offset": offset,
                    "has_more": bool(limit > 0 and len(rows) == limit),
                }
            )

        def _entry(self, path: str) -> None:
            encoded_hash = path[len("/api/entry/") :]
            if not encoded_hash or "/" in encoded_hash:
                self._json_error(HTTPStatus.NOT_FOUND, "entry not found")
                return
            content_hash = unquote(encoded_hash)
            if not content_hash or "/" in content_hash:
                self._json_error(HTTPStatus.NOT_FOUND, "entry not found")
                return
            result = inspection.entry(cache_root, content_hash)
            if result is None:
                self._json_error(HTTPStatus.NOT_FOUND, "entry not found")
                return
            self._send_json(result)

        def _objects(self, query: str) -> None:
            values = _single_query(query, {"orphans_only"})
            orphans_only = _boolean(values, "orphans_only")
            self._send_json(
                {
                    "rows": inspection.objects(cache_root, orphans_only=orphans_only),
                    "orphans_only": orphans_only,
                }
            )

        def _static(self, route: str) -> None:
            static_root = (Path(__file__).parent / "web").resolve()
            path = (static_root / _STATIC_ROUTES[route]).resolve()
            if not path.is_relative_to(static_root) or not path.is_file():
                self._json_error(HTTPStatus.NOT_FOUND, "asset not found")
                return
            try:
                body = path.read_bytes()
            except OSError:
                self._json_error(HTTPStatus.NOT_FOUND, "asset not found")
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
            }.get(path.suffix, "application/octet-stream")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", _JSON_CONTENT_TYPE)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            if status == HTTPStatus.METHOD_NOT_ALLOWED:
                self.send_header("Allow", "GET")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return CacheRequestHandler


def create_server(cache_root: Path, host: str, port: int) -> ThreadingHTTPServer:
    """Create, but do not start, the configured dashboard HTTP server."""
    root = Path(cache_root).expanduser().resolve()
    server = ThreadingHTTPServer((host, port), _handler_for(root))
    server.daemon_threads = True
    return server


def serve(cache_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the dashboard until interrupted, then close its listening socket."""
    server = create_server(cache_root, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
