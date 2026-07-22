"""Traefik service-label parsing."""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

HOST_CALL = re.compile(r"(?<![A-Za-z])Host\(\s*((?:`[^`]+`\s*,?\s*)+)\)")
LITERAL = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class RecordPlan:
    desired: dict[str, str]
    conflicts: set[str]
    ignored: tuple["IgnoredSource", ...] = ()


@dataclass(frozen=True)
class IgnoredSource:
    service: str
    label: str
    host: str
    reason: str


def normalize_host(host: str) -> str:
    return host.lower().rstrip(".")


def valid_hostname(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    labels = host.split(".")
    return all(
        0 < len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is not None
        for label in labels
    )


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


def extract_sources(source: object) -> list[str]:
    """Return explicit source hostnames from a unifi-dns.source label."""
    if not isinstance(source, str):
        return []
    hosts = []
    for value in re.split(r"[\s,]+", source):
        host = normalize_host(value.strip())
        if host:
            hosts.append(host)
    return hosts


def desired_records(
    services: list[dict[str, Any]],
    zones: tuple[str, ...] | list[str],
    default_target: str = "docker-swarm",
    with_conflicts: bool = False,
):
    """Produce desired hostname -> CNAME target, refusing ambiguous ownership."""
    plan = plan_records(services, zones, default_target)
    return (plan.desired, plan.conflicts) if with_conflicts else plan.desired


def plan_records(
    services: list[dict[str, Any]],
    zones: tuple[str, ...] | list[str],
    default_target: str = "docker-swarm",
) -> RecordPlan:
    """Plan desired hostname ownership from opted-in Traefik service labels."""
    normalized_zones = [normalize_host(zone) for zone in zones]
    claims = defaultdict(set)
    ignored = []
    for service in services:
        spec = service.get("Spec", {})
        service_name = spec.get("Name", "")
        labels = spec.get("Labels", {}) or {}
        if labels.get("unifi-dns.enable", "").lower() != "true":
            continue
        target = labels.get("unifi-dns.target", default_target).strip().lower()
        if not target or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", target):
            continue
        for host in extract_sources(labels.get("unifi-dns.source")):
            _claim_source(
                claims,
                ignored,
                service_name,
                "unifi-dns.source",
                host,
                target,
                normalized_zones,
            )
        for key, rule in labels.items():
            if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
                for host in extract_hosts(rule):
                    if _allowed(host, normalized_zones):
                        claims[host].add(target)
    conflicts = {host for host, targets in claims.items() if len(targets) > 1}
    desired = {host: next(iter(targets)) for host, targets in claims.items() if len(targets) == 1}
    return RecordPlan(desired=desired, conflicts=conflicts, ignored=tuple(ignored))


def _claim_source(
    claims,
    ignored: list[IgnoredSource],
    service_name: str,
    label: str,
    host: str,
    target: str,
    zones: list[str],
) -> None:
    if "*" in host:
        ignored.append(IgnoredSource(service_name, label, host, "wildcard source"))
        return
    if not valid_hostname(host):
        ignored.append(IgnoredSource(service_name, label, host, "invalid hostname"))
        return
    if not _allowed(host, zones):
        ignored.append(IgnoredSource(service_name, label, host, "outside allowed zones"))
        return
    claims[host].add(target)


def _allowed(host: str, zones: list[str]) -> bool:
    return any(host == zone or host.endswith("." + zone) for zone in zones)
