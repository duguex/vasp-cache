#!/usr/bin/env python3
"""Deterministic browser smoke checks for the read-only Materials Atlas.

This is an optional developer check: it uses an already-installed Playwright
package and never adds it to the application's runtime dependencies. API
responses are mocked in the browser so the checks can run against an empty
cache as well as a live dashboard URL.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "Browser smoke requires the optional Playwright Python package. "
        "Install it in the development environment (not the application) "
        "and run `playwright install chromium`.",
        file=sys.stderr,
    )
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[1]


def _fixture_rows(offset: int = 0) -> list[dict[str, object]]:
    return [
        {
            "content_hash": f"hash-{offset + index:02d}",
            "formula": "Si" if index % 2 == 0 else "Fe2O3",
            "task_name": f"relax-{offset + index:02d}",
            "provenance": "canonical",
            "provenance_source": "mapping",
            "total_energy": -10.25 - index,
            "converged": True,
            "nsites": 2,
            "cached_at": 1_700_000_000 + index,
        }
        for index in range(25)
    ]


def _api_payload(path: str, query: dict[str, list[str]]) -> dict[str, object]:
    if path == "/api/overview":
        return {
            "entries": 50,
            "formulas": 2,
            "with_energy": 50,
            "converged": 48,
            "with_bandgap": 40,
            "key_generations": {"5": 50},
            "provenance": {"canonical": 50, "unknown": 0},
            "storage_scan": False,
            "top_formulas": [{"formula": "Si", "entries": 25}, {"formula": "Fe2O3", "entries": 25}],
        }
    if path == "/api/entries":
        formula = query.get("formula", [""])[0]
        offset = int(query.get("offset", ["0"])[0])
        if formula == "NoSuchFormula":
            rows: list[dict[str, object]] = []
            has_more = False
        else:
            rows = _fixture_rows(offset)
            has_more = offset == 0
        return {"rows": rows, "limit": 25, "offset": offset, "has_more": has_more, "total": 50}
    if path.startswith("/api/entry/"):
        content_hash = path.rsplit("/", 1)[-1]
        return {
            "content_hash": content_hash,
            "formula": "Si",
            "task_name": "relax-00",
            "provenance": "canonical",
            "provenance_source": "mapping",
            "total_energy": -10.25,
            "converged": True,
            "nsites": 2,
            "max_abc": 5.43,
            "cached_at": 1_700_000_000,
            "key_generation": 5,
            "profile_id": "default",
            "mapping_digest": "mapping-digest",
            "source_dir": "/cache/Si/relax-00",
            "objects": {
                "vasprun.xml": {"digest": "cas-digest", "present": True, "size": 1024},
                "OUTCAR": {"digest": "missing-digest", "present": False, "size": None},
            },
        }
    if path == "/api/objects":
        return {"rows": [{"digest": "cas-digest", "present": True}], "orphans_only": False}
    raise AssertionError(f"Unexpected API route: {path}")


def _serve_dashboard() -> tuple[ThreadingHTTPServer, str, tempfile.TemporaryDirectory[str]]:
    from vasp_cache.web_server import create_server

    cache = tempfile.TemporaryDirectory(prefix="vasp-cache-browser-smoke-")
    server = create_server(Path(cache.name), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/", cache


def run_smoke(url: str) -> None:
    api_methods: list[str] = []
    load_events: list[str] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as error:
            raise SystemExit(
                "Browser smoke could not launch Chromium. Install the optional "
                "Playwright browser with `playwright install chromium`.\n"
                f"Underlying error: {error}"
            ) from error
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("load", lambda: load_events.append(page.url))

        def fulfill(route) -> None:
            request = route.request
            parsed = urlparse(request.url)
            if parsed.path.startswith("/api/"):
                api_methods.append(request.method)
                if request.method != "GET":
                    raise AssertionError(f"Dashboard attempted non-GET API request: {request.method} {request.url}")
                payload = _api_payload(parsed.path, parse_qs(parsed.query))
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
                return
            route.continue_()

        page.route("**/api/**", fulfill)
        page.goto(url, wait_until="networkidle")
        initial_load_count = len(load_events)

        # Overview and the approved masthead identity.
        assert page.locator(".masthead__topline").inner_text().startswith("VASP CACHE / MATERIALS ATLAS")
        assert page.locator("[data-testid='summary-metrics'] .metric").count() == 4
        assert page.locator("[data-testid='formula-families'] .family-row").count() == 2
        assert page.locator("#detail-drawer").get_attribute("aria-hidden") == "true"
        assert page.evaluate("document.querySelector('#detail-drawer').hidden && document.querySelector('#detail-drawer').getClientRects().length === 0")

        # Formula filtering must render the empty state without a full navigation.
        page.locator("#formula").fill("NoSuchFormula")
        page.wait_for_timeout(400)
        assert "No records match formula: NoSuchFormula" in page.locator("#catalog-state").inner_text()
        assert len(load_events) == initial_load_count, load_events
        page.locator("#formula").fill("Si")
        page.locator("#formula").press("Enter")
        page.wait_for_function("document.querySelectorAll('.catalog-row').length > 0")
        assert "formula=Si" in page.url
        assert len(load_events) == initial_load_count, load_events

        # Restore the catalog, then paginate through history.replaceState only.
        page.locator("#clear-filters").click()
        page.wait_for_function("!document.querySelector('#next-page').disabled")
        page.locator("#next-page").click()
        page.locator("#page-status").wait_for(state="visible")
        assert page.locator("#page-status").inner_text() == "PAGE 2"
        assert len(load_events) == initial_load_count, load_events
        assert urlparse(page.url).path == urlparse(url).path

        # Detail drawer exposes normalized identity and CAS presence status.
        page.locator(".catalog-row").first.click()
        page.locator("#detail-drawer").wait_for(state="visible")
        assert page.locator("#detail-drawer").get_attribute("aria-hidden") == "false"
        assert "Stored objects" in page.locator("#drawer-content").inner_text()
        assert "present" in page.locator("#drawer-content").inner_text()
        page.locator("#run-storage-scan").click()
        page.wait_for_function("document.querySelector('#storage-scan-result').textContent.includes('object records returned')")
        page.locator("#close-drawer").click()
        page.wait_for_timeout(40)
        page.locator(".catalog-row").first.dispatch_event("click")
        page.wait_for_function("document.querySelector('#detail-drawer').getAttribute('aria-hidden') === 'false'")
        page.wait_for_timeout(260)
        assert page.evaluate("!document.querySelector('#detail-drawer').hidden")
        page.locator("#close-drawer").click()

        # The drawer remains bounded at a narrow viewport and hidden after close.
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('#detail-drawer').hidden")
        assert page.locator("#detail-drawer").get_attribute("aria-hidden") == "true"
        assert page.locator("#detail-drawer").bounding_box() is None
        assert page.evaluate("document.querySelector('.detail-drawer').getBoundingClientRect().width <= innerWidth")

        assert api_methods and set(api_methods) == {"GET"}
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="dashboard URL (defaults to a temporary local dashboard)")
    args = parser.parse_args()
    server = None
    cache = None
    try:
        if args.url:
            url = args.url
        else:
            server, url, cache = _serve_dashboard()
        run_smoke(url)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if cache is not None:
            cache.cleanup()
    print("browser smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
