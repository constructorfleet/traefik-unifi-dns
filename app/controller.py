"""Reconcile opted-in Traefik router names into UniFi static DNS CNAMEs."""

import json
import logging
import time
from typing import Any

from .ports import StaticDnsProvider
from .traefik import RecordPlan, normalize_host, plan_records, valid_hostname, valid_target

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
        always_show_delete: bool = False,
    ) -> None:
        self.unifi, self.zones, self.ownership = unifi, zones, ownership
        self.default_target, self.localdomain = default_target, localdomain
        self.dry_run = dry_run
        self.require_enable_label = require_enable_label
        self.always_show_delete = always_show_delete
        self.conflicts, self.last_error, self.last_reconcile = set(), None, None
        self.ignored, self.claims = (), ()
        self.unifi_records = ()
        self.plan = RecordPlan(desired={}, conflicts=set())

    def target_domains(self) -> set[str]:
        targets = {self.default_target, *self.plan.desired.values()}
        targets.update(claim.target for claim in self.plan.skipped_claims)
        return {f"{target}.{self.localdomain}" for target in targets}

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
        self.unifi_records = tuple(records)
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

    def delete_stale_target_cname(self, hostname: str) -> str:
        record = next(
            (candidate for candidate in self.unifi_records if candidate.get("key") == hostname),
            None,
        )
        if (
            record is None
            or self._record_type(record) != "cname"
            or record.get("value") not in self.target_domains()
            or (hostname in self.plan.desired and not self.always_show_delete)
        ):
            raise ValueError("hostname is not a stale target CNAME")
        if self.dry_run:
            LOG.info(
                json.dumps(
                    {
                        "hostname": hostname,
                        "target": record.get("value"),
                        "action": "delete_stale_target_cname",
                        "result": "dry_run",
                    }
                )
            )
            return "dry_run"
        self.unifi.delete(hostname)
        self.ownership.pop(hostname, None)
        self.unifi_records = tuple(
            candidate for candidate in self.unifi_records if candidate.get("key") != hostname
        )
        LOG.info(
            json.dumps(
                {
                    "hostname": hostname,
                    "target": record.get("value"),
                    "action": "delete_stale_target_cname",
                    "result": "ok",
                }
            )
        )
        return "deleted"

    def add_cname(self, hostname: str, target: str | None = None) -> str:
        host = normalize_host(hostname.strip())
        cname_target = (target or self.default_target).strip().lower()
        if not valid_hostname(host) or not self._allowed(host):
            raise ValueError("hostname is invalid or outside allowed zones")
        if not valid_target(cname_target):
            raise ValueError("target must be a lowercase DNS label")
        fq_target = f"{cname_target}.{self.localdomain}"
        if self.dry_run:
            LOG.info(
                json.dumps(
                    {
                        "hostname": host,
                        "target": fq_target,
                        "action": "add_cname",
                        "result": "dry_run",
                    }
                )
            )
            return "dry_run"
        self.unifi.create(host, fq_target)
        self.ownership[host] = fq_target
        self.unifi_records = (
            *self.unifi_records,
            {"key": host, "value": fq_target, "record_type": "CNAME"},
        )
        LOG.info(
            json.dumps(
                {
                    "hostname": host,
                    "target": fq_target,
                    "action": "add_cname",
                    "result": "ok",
                }
            )
        )
        return "created"

    def _allowed(self, host: str) -> bool:
        return any(host == zone or host.endswith("." + zone) for zone in self.zones)

    def _record_type(self, record: dict[str, object]) -> str:
        return str(record.get("record_type", record.get("type", "cname"))).lower()
