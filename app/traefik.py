"""Traefik service-label parsing."""

import re
from collections import defaultdict
from typing import Any

HOST_CALL = re.compile(r"(?<![A-Za-z])Host\(\s*((?:`[^`]+`\s*,?\s*)+)\)")
LITERAL = re.compile(r"`([^`]+)`")


def normalize_host(host: str) -> str:
    return host.lower().rstrip(".")


def extract_hosts(rule: object) -> list[str]:
    """Return only literal, non-wildcard Host() arguments from a Traefik rule."""
    if not isinstance(rule, str):
        return []
    hosts = []
    for match in HOST_CALL.finditer(rule):
        values = LITERAL.findall(match.group(1))
        if not values or any("*" in value for value in values):
            continue
        hosts.extend(normalize_host(value) for value in values)
    return hosts


def desired_records(
    services: list[dict[str, Any]],
    zones: tuple[str, ...] | list[str],
    default_target: str = "docker-swarm",
    localdomain: str = "local",
    with_conflicts: bool = False,
):
    """Produce desired hostname -> CNAME target, refusing ambiguous ownership."""
    del localdomain
    normalized_zones = [normalize_host(zone) for zone in zones]
    claims = defaultdict(set)
    for service in services:
        labels = service.get("Spec", {}).get("Labels", {}) or {}
        if labels.get("unifi-dns.enable", "").lower() != "true":
            continue
        target = labels.get("unifi-dns.target", default_target).strip().lower()
        if not target or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", target):
            continue
        for key, rule in labels.items():
            if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
                for host in extract_hosts(rule):
                    if _allowed(host, normalized_zones):
                        claims[host].add(target)
    conflicts = {host for host, targets in claims.items() if len(targets) > 1}
    desired = {host: next(iter(targets)) for host, targets in claims.items() if len(targets) == 1}
    return (desired, conflicts) if with_conflicts else desired


def _allowed(host: str, zones: list[str]) -> bool:
    return any(host == zone or host.endswith("." + zone) for zone in zones)
