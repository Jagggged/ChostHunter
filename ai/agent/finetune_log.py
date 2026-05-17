"""Append-only log helpers for runtime fine-tuning runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai import config


def record_finetune_run(entry: dict, path: str = config.FINETUNE_RUN_LOG_PATH) -> dict:
    """Append one fine-tune scheduler event to the JSONL run log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=_json_default) + "\n")
    return entry


def read_finetune_runs(
    limit: int | None = None,
    path: str = config.FINETUNE_RUN_LOG_PATH,
) -> list[dict]:
    """Read fine-tune run entries newest first."""
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.reverse()
    if limit is not None:
        entries = entries[: max(limit, 0)]
    return entries


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    return str(value)
