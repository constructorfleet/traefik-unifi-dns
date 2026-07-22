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
        require_enable_label: bool = True,
    ) -> None:
        self.unifi, self.zones, self.ownership = unifi, zones, ownership
        self.default_target, self.localdomain = default_target, localdomain
        self.dry_run = dry_run
        self.require_enable_label = require_enable_label
        self.conflicts, self.last_error, self.last_reconcile = set(), None, None
        self.ignored, self.claims = (), ()
        self.plan = RecordPlan(desired={}, conflicts=set())

    def reconcile(self, services: list[dict[str, Any]]) -> None:
        plan = plan_records(
            services,
            self.zones,
            self.default_target,
            self.require_enable_label,
        )
        self.plan = plan
        self.conflicts = plan.conflicts
        self.ignored, self.claims = plan.ignored, plan.claims
        records = self.unifi.list()
        current = {record["key"]: record for record in records}
        LOG.info(
            json.dumps(
                {
                    "action": "plan",
                    "services": len(services),
                    "enabled_services": plan.enabled_services,
                    "skipped_services": plan.skipped_services,
                    "services_with_traefik_rules": plan.services_with_traefik_rules,
                    "claims": len(plan.claims),
                    "desired": len(plan.desired),
                    "conflicts": len(plan.conflicts),
                    "ignored": len(plan.ignored),
                    "unifi_records": len(records),
                    "owned_records": len(self.ownership),
                    "dry_run": self.dry_run,
                    "require_enable_label": self.require_enable_label,
                }
            )
        )
        for host, target in plan.desired.items():
            fq_target = target + "." + self.localdomain
            record = current.get(host)
            if record is None:
                if self.dry_run:
                    LOG.info(
                        json.dumps(
                            {
                                "hostname": host,
                                "target": fq_target,
                                "action": "create",
                                "result": "dry_run",
                            }
                        )
                    )
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
                    LOG.info(
                        json.dumps(
                            {
                                "hostname": host,
                                "target": fq_target,
                                "current_target": record.get("value"),
                                "action": "update",
                                "result": "dry_run",
                            }
                        )
                    )
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
                    LOG.info(
                        json.dumps(
                            {
                                "hostname": host,
                                "target": self.ownership[host],
                                "action": "delete",
                                "result": "dry_run",
                            }
                        )
                    )
                    continue
                if host in current:
                    self.unifi.delete(host)
                del self.ownership[host]
                LOG.info(json.dumps({"hostname": host, "action": "delete", "result": "ok"}))
        self.last_error, self.last_reconcile = None, time.time()
        LOG.info(
            json.dumps(
                {
                    "action": "reconcile",
                    "result": "ok",
                    "desired": len(plan.desired),
                    "conflicts": len(plan.conflicts),
                    "ignored": len(plan.ignored),
                    "owned_records": len(self.ownership),
                    "dry_run": self.dry_run,
                }
            )
        )
