# Task 1: Health collector

- **Status:** Complete. Added a read-only metadata collector and explicit bounded CAS scanner in `src/vasp_cache/health.py`, with deterministic bounded anomaly samples and energy review flags.
- **Tests:** `PYTHONPATH=src pytest tests/test_health.py -q` — 5 passed. Red-first collection run failed as expected with `ModuleNotFoundError: No module named 'vasp_cache.health'` before implementation. Also ran `PYTHONPATH=src python -m compileall -q src/vasp_cache/health.py tests/test_health.py` successfully.
- **Concerns:** CAS scanning intentionally validates only object presence and canonical path layout; it does not hash blob contents. Bounded scans report partial physical/orphan accounting and set `cas.limited` when the limit is reached.
- **Commit:** This report and the collector slice are committed together; see the final commit returned with the task status.
