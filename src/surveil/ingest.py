"""Download each CDC hub file with retries, validate it, and record checksums in a manifest."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from .config import RAW_DIR, SOURCES

log = logging.getLogger(__name__)


class IngestError(RuntimeError):
    pass


def _get(url: str, retries: int = 3) -> bytes:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except requests.RequestException as exc:
            if attempt == retries:
                raise IngestError(f"failed to download {url}: {exc}") from exc
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def ingest(raw_dir: Path = RAW_DIR, max_age_hours: float = 6, force: bool = False) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    mpath = raw_dir / "manifest.json"
    old = json.loads(mpath.read_text()) if mpath.exists() else {}
    manifest = {}
    for s in SOURCES.values():
        path = raw_dir / f"{s.name}.csv"
        fresh = path.exists() and (time.time() - path.stat().st_mtime) / 3600 < max_age_hours
        if fresh and not force and s.name in old:
            manifest[s.name] = old[s.name]
            log.info("cached  %-10s", s.name)
            continue
        body = _get(s.url)
        text = body.decode("utf-8", "replace")
        rows = text.count("\n")
        if rows < s.min_rows or text.lstrip().startswith("<"):
            raise IngestError(f"{s.name}: unexpected content ({rows} rows)")
        sha = hashlib.sha256(body).hexdigest()
        path.write_bytes(body)
        manifest[s.name] = {"url": s.url, "description": s.description, "rows": rows, "sha256": sha,
                            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                            "changed": sha != old.get(s.name, {}).get("sha256")}
        log.info("fetched %-10s %6d rows%s", s.name, rows, " (new data)" if manifest[s.name]["changed"] else "")
    mpath.write_text(json.dumps(manifest, indent=2))
    return manifest
