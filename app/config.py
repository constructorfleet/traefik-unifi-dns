"""Environment-driven application configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    docker_host: str
    unifi_url: str
    allowed_zones: tuple[str, ...]
    state_path: Path
    unifi_api_key_file: Path
    default_target: str
    cname_localdomain: str
    reconcile_interval_seconds: int
    port: int
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        unifi_url = values.get("UNIFI_URL", "").strip()
        allowed_zones = tuple(
            zone.strip()
            for zone in values.get("ALLOWED_ZONES", "").split(",")
            if zone.strip()
        )

        if not unifi_url:
            raise ValueError("UNIFI_URL is required")
        if not allowed_zones:
            raise ValueError("ALLOWED_ZONES must include at least one DNS zone")

        return cls(
            docker_host=values.get("DOCKER_HOST", "unix:///var/run/docker.sock").strip(),
            unifi_url=unifi_url,
            allowed_zones=allowed_zones,
            state_path=Path(values.get("STATE_PATH", "/state/ownership.json")),
            unifi_api_key_file=Path(values.get("UNIFI_API_KEY_FILE", "/run/secrets/unifi_api_key")),
            default_target=values.get("DEFAULT_TARGET", "docker-swarm").strip(),
            cname_localdomain=values.get("CNAME_LOCALDOMAIN", "local").strip(),
            reconcile_interval_seconds=int(values.get("RECONCILE_INTERVAL_SECONDS", "300")),
            port=int(values.get("PORT", "8080")),
            log_level=values.get("LOG_LEVEL", "INFO").strip(),
        )
