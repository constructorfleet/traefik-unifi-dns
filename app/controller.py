"""Reconcile opted-in Traefik router names into UniFi static DNS CNAMEs."""

import json
import logging
import time
from typing import Any

from .ports import StaticDnsProvider
from .traefik import RecordPlan, plan_records

LOG = logging.getLogger(__name__)


class Controller:
    def __init__(
        self,
        unifi: StaticDnsProvider,
        zones: tuple[str, ...] | list[str],
        ownership: dict[str, str],
        default_target: str = "docker-swarm",
        localdomain: str = "local",
        dry_run: bool = False,
    ) -> None:
        self.unifi, self.zones, self.ownership = unifi, zones, ownership
        self.default_target, self.localdomain = default_target, localdomain
        self.dry_run = dry_run
        self.conflicts, self.last_error, self.last_reconcile = set(), None, None
        self.ignored, self.claims = (), ()
        self.plan = RecordPlan(desired={}, conflicts=set())

    def reconcile(self, services: list[dict[str, Any]]) -> None:
        plan = plan_records(services, self.zones, self.default_target)
        self.plan = plan
        self.conflicts = plan.conflicts
        self.ignored, self.claims = plan.ignored, plan.claims
        current = {record["key"]: record for record in self.unifi.list()}
        for host, target in plan.desired.items():
            fq_target = target + "." + self.localdomain
            record = current.get(host)
            if record is None:
                if self.dry_run:
                    continue
                self.unifi.create(host, fq_target)
                self.ownership[host] = fq_target
                LOG.info(
                    json.dumps(
                        {"hostname": host, "target": fq_target, "action": "create", "result": "ok"}
                    )
                )
            elif self.ownership.get(host) and record.get("value") != fq_target:
                if self.dry_run:
                    continue
                self.unifi.update(host, fq_target)
                self.ownership[host] = fq_target
                LOG.info(
                    json.dumps(
                        {"hostname": host, "target": fq_target, "action": "update", "result": "ok"}
                    )
                )
        for host in list(self.ownership):
            if host not in plan.desired and host not in self.conflicts:
                if self.dry_run:
                    continue
                if host in current:
                    self.unifi.delete(host)
                del self.ownership[host]
                LOG.info(json.dumps({"hostname": host, "action": "delete", "result": "ok"}))
        self.last_error, self.last_reconcile = None, time.time()
