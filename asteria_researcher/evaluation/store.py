"""Durable, local persistence for evaluation assets.

The first implementation deliberately uses JSONL rather than introducing a
database.  It keeps the data portable, reviewable, and close to the format
used by GoodQuestion/OpenTelemetry exports while still providing safe
upserts for a local development server.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class EvaluationStore:
    COLLECTIONS = (
        "traces", "badcases", "seeds", "cases", "tasks",
        "generated_cases", "results", "reports",
    )

    def __init__(self, root: str | Path | None = None):
        default = Path(__file__).resolve().parents[2] / "outputs" / "evaluation"
        self.root = Path(root or os.getenv("ASTERIA_EVAL_DATA_DIR", default))
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _path(self, collection: str) -> Path:
        if collection not in self.COLLECTIONS:
            raise ValueError(f"unsupported evaluation collection: {collection}")
        return self.root / f"{collection}.jsonl"

    def _dump(self, value: Any) -> dict[str, Any]:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        raise TypeError("evaluation records must be Pydantic models or dictionaries")

    def _key(self, collection: str, record: dict[str, Any]) -> str:
        names = {
            "traces": "trace_id", "badcases": "badcase_id", "seeds": "seed_id",
            "cases": "case_id", "tasks": "task_id", "generated_cases": "generated_id",
            "results": "result_id", "reports": "task_id",
        }
        return str(record.get(names[collection], ""))

    def append(self, collection: str, value: Any) -> dict[str, Any]:
        record = self._dump(value)
        with self._lock, self._path(collection).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def upsert(self, collection: str, value: Any) -> dict[str, Any]:
        record = self._dump(value)
        key = self._key(collection, record)
        if not key:
            return self.append(collection, record)
        with self._lock:
            records = [item for item in self._read(collection) if self._key(collection, item) != key]
            records.append(record)
            self._rewrite(collection, records)
        return record

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            for record in reversed(self._read(collection)):
                if self._key(collection, record) == record_id:
                    return record
        return None

    def list(self, collection: str, *, limit: int | None = None, **filters: Any) -> list[dict[str, Any]]:
        with self._lock:
            records = self._read(collection)
        for key, expected in filters.items():
            if expected is None:
                continue
            records = [item for item in records if item.get(key) == expected]
        records.reverse()
        return records[:limit] if limit else records

    def delete(self, collection: str, record_id: str) -> bool:
        with self._lock:
            records = self._read(collection)
            kept = [item for item in records if self._key(collection, item) != record_id]
            if len(kept) == len(records):
                return False
            self._rewrite(collection, kept)
            return True

    def _read(self, collection: str) -> list[dict[str, Any]]:
        path = self._path(collection)
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def _rewrite(self, collection: str, records: Iterable[dict[str, Any]]) -> None:
        destination = self._path(collection)
        fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
