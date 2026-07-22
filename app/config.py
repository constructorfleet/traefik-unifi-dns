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
    unifi_verify_ssl: bool
    allowed_zones: tuple[str, ...]
    state_path: Path
    unifi_api_key_file: Path
    default_target: str
    cname_localdomain: str
    dry_run: bool
    require_unifi_dns_enable: bool
    always_show_delete: bool
    reconcile_interval_seconds: int
    port: int
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        unifi_url = _env_value(values, "UNIFI_URL", "").strip()
        unifi_verify_ssl = _parse_bool(
            _env_value(values, "UNIFI_VERIFY_SSL", "true"),
            "UNIFI_VERIFY_SSL",
        )
        allowed_zones = tuple(
            normalize_host(zone.strip())
            for zone in _env_value(values, "ALLOWED_ZONES", "").split(",")
            if zone.strip()
        )
        default_target = _env_value(values, "DEFAULT_TARGET", "docker-swarm").strip().lower()
        cname_localdomain = normalize_host(_env_value(values, "CNAME_LOCALDOMAIN", "local").strip())
        dry_run = _parse_bool(_env_value(values, "DRY_RUN", "false"), "DRY_RUN")
        require_unifi_dns_enable = _parse_bool(
            _env_value(values, "REQUIRE_UNIFI_DNS_ENABLE", "true"),
            "REQUIRE_UNIFI_DNS_ENABLE",
        )
        always_show_delete = _parse_bool(
            _env_value(values, "ALWAYS_SHOW_DELETE", "false"),
            "ALWAYS_SHOW_DELETE",
        )
        reconcile_interval_seconds = _parse_positive_int(
            _env_value(values, "RECONCILE_INTERVAL_SECONDS", "300"),
            "RECONCILE_INTERVAL_SECONDS",
        )
        port = _parse_port(_env_value(values, "PORT", "8080"))
        log_level = _env_value(values, "LOG_LEVEL", "INFO").strip().upper()

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
            docker_host=_env_value(values, "DOCKER_HOST", "unix:///var/run/docker.sock").strip(),
            unifi_url=unifi_url,
            unifi_verify_ssl=unifi_verify_ssl,
            allowed_zones=allowed_zones,
            state_path=Path(_env_value(values, "STATE_PATH", "/state/ownership.json")),
            unifi_api_key_file=Path(
                _env_value(values, "UNIFI_API_KEY_FILE", "/run/secrets/unifi_api_key")
            ),
            default_target=default_target,
            cname_localdomain=cname_localdomain,
            dry_run=dry_run,
            require_unifi_dns_enable=require_unifi_dns_enable,
            always_show_delete=always_show_delete,
            reconcile_interval_seconds=reconcile_interval_seconds,
            port=port,
            log_level=log_level,
        )


def _env_value(values: Mapping[str, str], name: str, default: str) -> str:
    file_name = f"{name}_FILE"
    has_value = name in values and values[name] != ""
    has_file = file_name in values and values[file_name] != ""
    if has_value and has_file:
        raise ValueError(f"{name} and {file_name} cannot both be set")
    if has_file:
        path = Path(values[file_name])
        try:
            return path.read_text().strip()
        except OSError as error:
            raise ValueError(f"{file_name} could not be read: {path}") from error
    return values.get(name, default)


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
