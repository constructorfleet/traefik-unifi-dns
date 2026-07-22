"""Docker Engine API adapter."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import requests
import requests_unixsocket


class DockerClient:
    def __init__(self, endpoint: str, api_version: str = "v1.41") -> None:
        self.session = self._session_for(endpoint)
        self.base_url = self._base_url(endpoint, api_version)

    def list_services(self) -> list[dict[str, Any]]:
        response = self.session.get(f"{self.base_url}/services", timeout=15)
        response.raise_for_status()
        return response.json()

    def stream_service_events(self):
        return self.session.get(
            f"{self.base_url}/events",
            params={"filters": json.dumps({"type": ["service"]})},
            stream=True,
            timeout=70,
        )

    @staticmethod
    def _session_for(endpoint: str):
        if endpoint.startswith("unix://"):
            return requests_unixsocket.Session()
        return requests.Session()

    @staticmethod
    def _base_url(endpoint: str, api_version: str) -> str:
        if endpoint.startswith("unix://"):
            socket_path = endpoint.removeprefix("unix://").replace("/", "%2F")
            return f"http+unix://{socket_path}/{api_version}"
        return f"{endpoint.rstrip('/')}/{api_version}"
