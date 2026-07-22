"""Environment-driven application configuration."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .traefik import normalize_host, valid_hostname, valid_target


@dataclass(frozen=True)
class Settings:
    docker_host: str
    unifi_url: str
    allowed_zones: tuple[str, ...]
    state_path: Path
    unifi_api_key_file: Path
    default_target: str
    cname_localdomain: str
    dry_run: bool
    reconcile_interval_seconds: int
    port: int
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        unifi_url = values.get("UNIFI_URL", "").strip()
        allowed_zones = tuple(
            normalize_host(zone.strip())
            for zone in values.get("ALLOWED_ZONES", "").split(",")
            if zone.strip()
        )
        default_target = values.get("DEFAULT_TARGET", "docker-swarm").strip().lower()
        cname_localdomain = normalize_host(values.get("CNAME_LOCALDOMAIN", "local").strip())
        dry_run = _parse_bool(values.get("DRY_RUN", "false"), "DRY_RUN")
        reconcile_interval_seconds = _parse_positive_int(
            values.get("RECONCILE_INTERVAL_SECONDS", "300"),
            "RECONCILE_INTERVAL_SECONDS",
        )
        port = _parse_port(values.get("PORT", "8080"))
        log_level = values.get("LOG_LEVEL", "INFO").strip().upper()

        if not unifi_url:
            raise ValueError("UNIFI_URL is required")
        if not allowed_zones:
            raise ValueError("ALLOWED_ZONES must include at least one DNS zone")
        invalid_zones = [zone for zone in allowed_zones if not valid_hostname(zone)]
        if invalid_zones:
            raise ValueError(f"ALLOWED_ZONES contains invalid DNS zone: {invalid_zones[0]}")
        if not valid_target(default_target):
            raise ValueError("DEFAULT_TARGET must be a lowercase DNS label target")
        if not valid_hostname(cname_localdomain):
            raise ValueError("CNAME_LOCALDOMAIN must be a valid DNS suffix")
        if log_level not in logging.getLevelNamesMapping():
            raise ValueError("LOG_LEVEL must be a standard Python logging level name")

        return cls(
            docker_host=values.get("DOCKER_HOST", "unix:///var/run/docker.sock").strip(),
            unifi_url=unifi_url,
            allowed_zones=allowed_zones,
            state_path=Path(values.get("STATE_PATH", "/state/ownership.json")),
            unifi_api_key_file=Path(values.get("UNIFI_API_KEY_FILE", "/run/secrets/unifi_api_key")),
            default_target=default_target,
            cname_localdomain=cname_localdomain,
            dry_run=dry_run,
            reconcile_interval_seconds=reconcile_interval_seconds,
            port=port,
            log_level=log_level,
        )


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _parse_port(value: str) -> int:
    port = _parse_positive_int(value, "PORT")
    if port > 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return port
