"""Diagnostic logging + append-only JSONL audit trail.

Two channels
------------
1. **stdlib logging** (``vasp_cache.*``) — human diagnostics on stderr/file.
2. **audit JSONL** — one JSON object per line for put/has/fetch/… outcomes.

Enable
------
- CLI: ``vasp-cache -v …`` / ``vasp-cache --audit-log PATH …``
- Env: ``VASP_CACHE_LOG_LEVEL=DEBUG|INFO|WARNING``
        ``VASP_CACHE_AUDIT_LOG=/path/to/audit.jsonl``
        ``VASP_CACHE_AUDIT=0`` to disable JSONL even if path set
- API: ``setup_logging(level="DEBUG")`` / ``set_audit_log(path)``

Default audit path (when enabled without explicit path):
``$VASP_CACHE_ROOT/logs/audit.jsonl``.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

_LOG_CONFIGURED = False
_audit_path: Path | None = None
_audit_enabled: bool = True
_audit_lock = threading.Lock()
_host = socket.gethostname()
_pid = os.getpid()

logger = logging.getLogger("vasp_cache.audit")


def setup_logging(
    level: str | int | None = None,
    *,
    stream: bool = True,
) -> None:
    """Configure root-ish ``vasp_cache`` loggers once.

    *level*: ``DEBUG``/``INFO``/… or int. Default from ``VASP_CACHE_LOG_LEVEL``
    or INFO.
    """
    global _LOG_CONFIGURED
    if level is None:
        level = os.environ.get("VASP_CACHE_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("vasp_cache")
    root.setLevel(level)

    if not _LOG_CONFIGURED and stream:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
        # avoid double if root also has handlers
        root.propagate = False
        _LOG_CONFIGURED = True
    else:
        root.setLevel(level)
        for h in root.handlers:
            h.setLevel(level)


def set_audit_log(path: Path | str | None) -> None:
    """Set JSONL audit path. ``None`` clears explicit path (env/default may still apply)."""
    global _audit_path
    _audit_path = Path(path).expanduser().resolve() if path else None


def enable_audit(on: bool = True) -> None:
    global _audit_enabled
    _audit_enabled = on


def resolve_audit_path(cache_root: Path | None = None) -> Path | None:
    """Return active audit log path, or None if auditing disabled."""
    if not _audit_enabled:
        return None
    env_off = os.environ.get("VASP_CACHE_AUDIT", "1").strip().lower()
    if env_off in ("0", "false", "no", "off"):
        return None
    if _audit_path is not None:
        return _audit_path
    env = os.environ.get("VASP_CACHE_AUDIT_LOG")
    if env:
        return Path(env).expanduser().resolve()
    if cache_root is not None:
        return Path(cache_root) / "logs" / "audit.jsonl"
    # lazy default via cache_root()
    try:
        from vasp_cache.paths import cache_root as _cr

        return _cr() / "logs" / "audit.jsonl"
    except Exception:
        return None


def audit(event: str, **fields: Any) -> None:
    """Append one audit event (JSONL) and mirror at INFO/DEBUG.

    Always safe: failures to write audit never raise to callers.
    """
    payload: dict[str, Any] = {
        "ts": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "event": event,
        "host": _host,
        "pid": _pid,
        "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "",
    }
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, Path):
            payload[k] = str(v)
        else:
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = str(v)

    # human diagnostic line
    summary = " ".join(
        f"{k}={payload[k]}"
        for k in ("event", "dir", "content_hash", "reason", "hit", "formula", "n")
        if k in payload
    )
    if event.endswith("_skip") or event.endswith("_miss") or event.endswith("_error"):
        logger.info("%s", summary)
    else:
        logger.info("%s", summary)

    path = resolve_audit_path(
        Path(fields["cache_root"]) if fields.get("cache_root") else None
    )
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        with _audit_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError as exc:
        logger.warning("audit write failed path=%s err=%s", path, exc)


def reset_for_tests() -> None:
    """Clear audit path and logging flag (tests only)."""
    global _audit_path, _LOG_CONFIGURED, _audit_enabled
    _audit_path = None
    _audit_enabled = True
    _LOG_CONFIGURED = False
    # remove handlers from vasp_cache logger
    root = logging.getLogger("vasp_cache")
    for h in list(root.handlers):
        root.removeHandler(h)
