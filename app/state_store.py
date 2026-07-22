"""Persistent ownership-state storage."""

from __future__ import annotations

import json
from pathlib import Path


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        body = self._load_body()
        if "ownership" in body and isinstance(body["ownership"], dict):
            return _string_map(body["ownership"])
        return _string_map(body)

    def load_manual_metadata(self) -> dict[str, dict[str, str]]:
        body = self._load_body()
        if not isinstance(body.get("manual_metadata"), dict):
            return {}
        return {
            str(host): {
                "stack": str(metadata.get("stack", "")),
                "service": str(metadata.get("service", "")),
            }
            for host, metadata in body["manual_metadata"].items()
            if isinstance(metadata, dict)
        }

    def save(
        self,
        ownership: dict[str, str],
        manual_metadata: dict[str, dict[str, str]] | None = None,
    ) -> None:
        if manual_metadata is None:
            manual_metadata = self.load_manual_metadata()
        state = {
            "ownership": ownership,
            "manual_metadata": manual_metadata,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, sort_keys=True))

    def _load_body(self) -> dict:
        try:
            body = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        return body if isinstance(body, dict) else {}


def _string_map(value: dict) -> dict[str, str]:
    return {str(key): str(item) for key, item in value.items()}
