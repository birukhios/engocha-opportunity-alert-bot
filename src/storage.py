"""JSON-backed storage for seen and sent opportunities."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


LOGGER = logging.getLogger(__name__)

DATA_DIR = Path("data")
SEEN_PATH = DATA_DIR / "seen.json"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"


def make_opportunity_id(title: str, link: str) -> str:
    raw = f"{title.strip()}|{link.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_seen(path: Path = SEEN_PATH) -> set[str]:
    data = _read_json(path, default={"sent_ids": []})
    if isinstance(data, list):
        return set(str(item) for item in data)
    return set(str(item) for item in data.get("sent_ids", []))


def load_opportunities(path: Path = OPPORTUNITIES_PATH) -> list[dict]:
    data = _read_json(path, default=[])
    return data if isinstance(data, list) else []


def save_seen(seen_ids: Iterable[str], path: Path = SEEN_PATH) -> None:
    payload = {
        "sent_ids": sorted(set(seen_ids)),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_json(path, payload)


def save_opportunities(opportunities: list[dict], path: Path = OPPORTUNITIES_PATH) -> None:
    deduped: dict[str, dict] = {}
    for opportunity in opportunities:
        opportunity_id = opportunity.get("id")
        if opportunity_id:
            deduped[opportunity_id] = opportunity

    ordered = sorted(
        deduped.values(),
        key=lambda item: (item.get("date_found", ""), item.get("score", 0), item.get("title", "")),
        reverse=True,
    )
    _write_json(path, ordered)


def append_sent_opportunities(new_items: list[dict]) -> None:
    existing = load_opportunities()
    save_opportunities(existing + new_items)


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SEEN_PATH.exists():
        save_seen(set())
    if not OPPORTUNITIES_PATH.exists():
        save_opportunities([])


def _read_json(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("Could not parse %s; using default empty data.", path)
        return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp_path, path)
