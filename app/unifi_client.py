"""UniFi Network static DNS adapter."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class UnifiStaticDnsClient:
    def __init__(self, base_url: str, api_key_file: Path) -> None:
        self.url = base_url.rstrip("/") + "/proxy/network/v2/api/site/default/static-dns"
        self.headers = {"X-API-Key": api_key_file.read_text().strip()}

    def list(self) -> list[dict[str, Any]]:
        response = requests.get(self.url, headers=self.headers, timeout=20)
        response.raise_for_status()
        body = response.json()
        return body.get("data", body if isinstance(body, list) else [])

    def create(self, host: str, target: str) -> None:
        self._write("post", {"key": host, "value": target, "type": "cname"})

    def update(self, host: str, target: str) -> None:
        self._write("put", {"key": host, "value": target, "type": "cname"})

    def delete(self, host: str) -> None:
        response = requests.delete(f"{self.url}/{host}", headers=self.headers, timeout=20)
        response.raise_for_status()

    def _write(self, method: str, payload: dict[str, str]) -> None:
        response = getattr(requests, method)(
            self.url,
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
