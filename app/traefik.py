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
    claims: tuple["SourceClaim", ...] = ()
    skipped_claims: tuple["SourceClaim", ...] = ()
    enabled_services: int = 0
    skipped_services: int = 0
    services_with_traefik_rules: int = 0


@dataclass(frozen=True)
class SourceClaim:
    host: str
    target: str
    service: str
    stack: str
    label: str
    kind: str


@dataclass(frozen=True)
class IgnoredSource:
    service: str
    stack: str
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


def valid_target(target: str) -> bool:
    return re.fullmatch(r"[a-z0-9][a-z0-9-]*", target) is not None


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
    require_enable_label: bool = True,
):
    """Produce desired hostname -> CNAME target, refusing ambiguous ownership."""
    plan = plan_records(services, zones, default_target, require_enable_label)
    return (plan.desired, plan.conflicts) if with_conflicts else plan.desired


def plan_records(
    services: list[dict[str, Any]],
    zones: tuple[str, ...] | list[str],
    default_target: str = "docker-swarm",
    require_enable_label: bool = True,
) -> RecordPlan:
    """Plan desired hostname ownership from opted-in Traefik service labels."""
    normalized_zones = [normalize_host(zone) for zone in zones]
    claims = defaultdict(set)
    source_claims = []
    skipped_claims = []
    ignored = []
    enabled_services = 0
    skipped_services = 0
    services_with_traefik_rules = 0
    for service in services:
        spec = service.get("Spec", {})
        service_name = spec.get("Name", "")
        labels = spec.get("Labels", {}) or {}
        stack_name = labels.get("com.docker.stack.namespace", "")
        has_traefik_rules = any(
            key.startswith("traefik.http.routers.") and key.endswith(".rule") for key in labels
        )
        if has_traefik_rules:
            services_with_traefik_rules += 1
        target = labels.get("unifi-dns.target", default_target).strip().lower()
        if not target or not valid_target(target):
            continue
        if require_enable_label and not _unifi_dns_enabled(labels):
            skipped_services += 1
            skipped_claims.extend(
                _service_traefik_claims(
                    labels,
                    service_name,
                    stack_name,
                    target,
                )
            )
            continue
        enabled_services += 1
        for key, source in labels.items():
            source_target = _source_label_target(key, target)
            if source_target is None:
                continue
            for host in extract_sources(source):
                if not valid_target(source_target):
                    ignored.append(
                        IgnoredSource(service_name, stack_name, key, host, "invalid target")
                    )
                    continue
                _claim_source(
                    claims,
                    source_claims,
                    ignored,
                    service_name,
                    stack_name,
                    key,
                    host,
                    source_target,
                    normalized_zones,
                    "manual",
                )
        for key, rule in labels.items():
            if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
                for host in extract_hosts(rule):
                    _claim_source(
                        claims,
                        source_claims,
                        ignored,
                        service_name,
                        stack_name,
                        key,
                        host,
                        target,
                        normalized_zones,
                        "traefik",
                    )
    conflicts = {host for host, targets in claims.items() if len(targets) > 1}
    desired = {host: next(iter(targets)) for host, targets in claims.items() if len(targets) == 1}
    return RecordPlan(
        desired=desired,
        conflicts=conflicts,
        ignored=tuple(ignored),
        claims=tuple(source_claims),
        skipped_claims=tuple(skipped_claims),
        enabled_services=enabled_services,
        skipped_services=skipped_services,
        services_with_traefik_rules=services_with_traefik_rules,
    )


def _claim_source(
    claims,
    source_claims: list[SourceClaim],
    ignored: list[IgnoredSource],
    service_name: str,
    stack_name: str,
    label: str,
    host: str,
    target: str,
    zones: list[str],
    kind: str,
) -> None:
    if "*" in host:
        ignored.append(IgnoredSource(service_name, stack_name, label, host, "wildcard source"))
        return
    if not valid_hostname(host):
        ignored.append(IgnoredSource(service_name, stack_name, label, host, "invalid hostname"))
        return
    if not _allowed(host, zones):
        ignored.append(
            IgnoredSource(service_name, stack_name, label, host, "outside allowed zones")
        )
        return
    claims[host].add(target)
    source_claims.append(SourceClaim(host, target, service_name, stack_name, label, kind))


def _source_label_target(label: str, default_target: str) -> str | None:
    if label == "unifi-dns.source":
        return default_target
    prefix = "unifi-dns.source."
    if label.startswith(prefix):
        return label[len(prefix) :].strip().lower()
    return None


def _unifi_dns_enabled(labels: dict[str, str]) -> bool:
    return (
        labels.get("unifi-dns.enable", "").lower() == "true"
        or labels.get("unifi-dns.enabled", "").lower() == "true"
    )


def _service_traefik_claims(
    labels: dict[str, str],
    service_name: str,
    stack_name: str,
    target: str,
) -> list[SourceClaim]:
    claims = []
    for key, rule in labels.items():
        if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
            claims.extend(
                SourceClaim(host, target, service_name, stack_name, key, "traefik")
                for host in extract_hosts(rule)
            )
    return claims


def _allowed(host: str, zones: list[str]) -> bool:
    return any(host == zone or host.endswith("." + zone) for zone in zones)
