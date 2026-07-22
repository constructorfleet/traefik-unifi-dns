"""Reconcile opted-in Traefik router names into UniFi static DNS CNAMEs."""

import json
import logging
import re
import time
from collections import defaultdict

LOG = logging.getLogger(__name__)
HOST_CALL = re.compile(r"(?<![A-Za-z])Host\(\s*((?:`[^`]+`\s*,?\s*)+)\)")
LITERAL = re.compile(r"`([^`]+)`")


def normalize_host(host):
    return host.lower().rstrip(".")


def extract_hosts(rule):
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


def _allowed(host, zones):
    return any(host == zone or host.endswith("." + zone) for zone in zones)


def desired_records(
    services, zones, default_target="docker-swarm", localdomain="local", with_conflicts=False
):
    """Produce desired hostname -> CNAME target, refusing ambiguous ownership."""
    zones = [normalize_host(zone) for zone in zones]
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
                    if _allowed(host, zones):
                        claims[host].add(target)
    conflicts = {host for host, targets in claims.items() if len(targets) > 1}
    desired = {host: next(iter(targets)) for host, targets in claims.items() if len(targets) == 1}
    return (desired, conflicts) if with_conflicts else desired


class Controller:
    def __init__(self, unifi, zones, ownership, default_target="docker-swarm", localdomain="local"):
        self.unifi, self.zones, self.ownership = unifi, zones, ownership
        self.default_target, self.localdomain = default_target, localdomain
        self.conflicts, self.last_error, self.last_reconcile = set(), None, None

    def reconcile(self, services):
        desired, self.conflicts = desired_records(
            services, self.zones, self.default_target, self.localdomain, True
        )
        current = {record["key"]: record for record in self.unifi.list()}
        for host, target in desired.items():
            fq_target = target + "." + self.localdomain
            record = current.get(host)
            if record is None:
                self.unifi.create(host, fq_target)
                self.ownership[host] = fq_target
                LOG.info(
                    json.dumps(
                        {"hostname": host, "target": fq_target, "action": "create", "result": "ok"}
                    )
                )
            elif self.ownership.get(host) and record.get("value") != fq_target:
                self.unifi.update(host, fq_target)
                self.ownership[host] = fq_target
                LOG.info(
                    json.dumps(
                        {"hostname": host, "target": fq_target, "action": "update", "result": "ok"}
                    )
                )
        for host in list(self.ownership):
            if host not in desired and host not in self.conflicts:
                if host in current:
                    self.unifi.delete(host)
                del self.ownership[host]
                LOG.info(json.dumps({"hostname": host, "action": "delete", "result": "ok"}))
        self.last_error, self.last_reconcile = None, time.time()
