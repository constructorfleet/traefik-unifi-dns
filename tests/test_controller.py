import unittest

from app.controller import Controller
from app.traefik import desired_records, extract_hosts, normalize_host, plan_records, valid_hostname


class RuleExtractionTests(unittest.TestCase):
    def test_extracts_one_host(self):
        self.assertEqual(
            extract_hosts("Host(`app.home.prettybaked.com`)"), ["app.home.prettybaked.com"]
        )

    def test_extracts_multiple_hosts_and_compound_rules(self):
        rule = "Host(`a.home.prettybaked.com`, `b.home.prettybaked.com`) && PathPrefix(`/`)"
        self.assertEqual(extract_hosts(rule), ["a.home.prettybaked.com", "b.home.prettybaked.com"])

    def test_rejects_regexp_wildcards_and_invalid_syntax(self):
        self.assertEqual(extract_hosts("HostRegexp(`{subdomain:.+}.example.com`)"), [])
        self.assertEqual(extract_hosts("Host(`*.home.prettybaked.com`)"), [])
        self.assertEqual(extract_hosts("Host(app.home.prettybaked.com)"), [])

    def test_normalizes_and_allowlists(self):
        self.assertEqual(normalize_host("APP.HOME.PRETTYBAKED.COM."), "app.home.prettybaked.com")
        services = [
            {
                "Spec": {
                    "Name": "app",
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "traefik.http.routers.app.rule": "Host(`APP.HOME.PRETTYBAKED.COM.`)",
                    },
                }
            }
        ]
        self.assertEqual(
            desired_records(services, ["home.prettybaked.com"]),
            {"app.home.prettybaked.com": "docker-swarm"},
        )

    def test_target_override_duplicate_and_conflict(self):
        def svc(name, target):
            return {
                "Spec": {
                    "Name": name,
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "unifi-dns.target": target,
                        "traefik.http.routers.r.rule": "Host(`same.home.prettybaked.com`)",
                    },
                }
            }

        desired, conflicts = desired_records(
            [svc("a", "one"), svc("b", "two")], ["home.prettybaked.com"], with_conflicts=True
        )
        self.assertEqual(desired, {})
        self.assertEqual(conflicts, {"same.home.prettybaked.com"})

    def test_record_plan_exposes_desired_records_and_conflicts(self):
        plan = plan_records(
            [
                service("app", "Host(`app.home.prettybaked.com`)", "docker-swarm"),
                service("dup-a", "Host(`dup.home.prettybaked.com`)", "one"),
                service("dup-b", "Host(`dup.home.prettybaked.com`)", "two"),
            ],
            ["home.prettybaked.com"],
        )

        self.assertEqual(plan.desired, {"app.home.prettybaked.com": "docker-swarm"})
        self.assertEqual(plan.conflicts, {"dup.home.prettybaked.com"})
        self.assertEqual(
            [(claim.service, claim.kind, claim.label, claim.target) for claim in plan.claims],
            [
                ("app", "traefik", "traefik.http.routers.app.rule", "docker-swarm"),
                ("dup-a", "traefik", "traefik.http.routers.app.rule", "one"),
                ("dup-b", "traefik", "traefik.http.routers.app.rule", "two"),
            ],
        )
        self.assertEqual(plan.enabled_services, 3)
        self.assertEqual(plan.skipped_services, 0)
        self.assertEqual(plan.services_with_traefik_rules, 3)

    def test_traefik_rule_without_unifi_opt_in_is_skipped(self):
        plan = plan_records(
            [
                {
                    "Spec": {
                        "Name": "app",
                        "Labels": {
                            "traefik.enable": "true",
                            "traefik.http.routers.app.rule": ("Host(`app.home.prettybaked.com`)"),
                        },
                    }
                }
            ],
            ["home.prettybaked.com"],
        )

        self.assertEqual(plan.desired, {})
        self.assertEqual(plan.claims, ())
        self.assertEqual(plan.enabled_services, 0)
        self.assertEqual(plan.skipped_services, 1)
        self.assertEqual(plan.services_with_traefik_rules, 1)

    def test_bypass_unifi_opt_in_processes_traefik_rules(self):
        plan = plan_records(
            [
                {
                    "Spec": {
                        "Name": "app",
                        "Labels": {
                            "traefik.enable": "true",
                            "traefik.http.routers.app.rule": ("Host(`app.home.prettybaked.com`)"),
                        },
                    }
                }
            ],
            ["home.prettybaked.com"],
            require_enable_label=False,
        )

        self.assertEqual(plan.desired, {"app.home.prettybaked.com": "docker-swarm"})
        self.assertEqual(plan.enabled_services, 1)
        self.assertEqual(plan.skipped_services, 0)
        self.assertEqual(plan.services_with_traefik_rules, 1)

    def test_source_label_adds_manual_hosts(self):
        services = [
            {
                "Spec": {
                    "Name": "app",
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "unifi-dns.source": (
                            "manual.home.prettybaked.com,extra.home.prettybaked.com"
                        ),
                    },
                }
            }
        ]

        self.assertEqual(
            desired_records(services, ["home.prettybaked.com"]),
            {
                "manual.home.prettybaked.com": "docker-swarm",
                "extra.home.prettybaked.com": "docker-swarm",
            },
        )

    def test_source_target_suffix_overrides_service_target(self):
        services = [
            {
                "Spec": {
                    "Name": "app",
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "unifi-dns.target": "docker-swarm",
                        "unifi-dns.source.edge": "edge.home.prettybaked.com",
                        "unifi-dns.source.media": "media.home.prettybaked.com",
                    },
                }
            }
        ]

        plan = plan_records(services, ["home.prettybaked.com"])

        self.assertEqual(
            plan.desired,
            {
                "edge.home.prettybaked.com": "edge",
                "media.home.prettybaked.com": "media",
            },
        )
        self.assertEqual(
            [(claim.host, claim.target, claim.label) for claim in plan.claims],
            [
                ("edge.home.prettybaked.com", "edge", "unifi-dns.source.edge"),
                ("media.home.prettybaked.com", "media", "unifi-dns.source.media"),
            ],
        )

    def test_invalid_source_target_suffix_is_ignored(self):
        services = [
            {
                "Spec": {
                    "Name": "app",
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "unifi-dns.source.bad_target": "app.home.prettybaked.com",
                    },
                }
            }
        ]

        plan = plan_records(services, ["home.prettybaked.com"])

        self.assertEqual(plan.desired, {})
        self.assertEqual(
            [(ignored.label, ignored.host, ignored.reason) for ignored in plan.ignored],
            [("unifi-dns.source.bad_target", "app.home.prettybaked.com", "invalid target")],
        )

    def test_source_label_still_requires_allowed_zone(self):
        services = [
            {
                "Spec": {
                    "Name": "app",
                    "Labels": {
                        "unifi-dns.enable": "true",
                        "unifi-dns.source": "manual.home.prettybaked.com,manual.example.net",
                    },
                }
            }
        ]

        self.assertEqual(
            desired_records(services, ["home.prettybaked.com"]),
            {"manual.home.prettybaked.com": "docker-swarm"},
        )

    def test_rejects_malformed_source_hostnames_with_reasons(self):
        plan = plan_records(
            [
                {
                    "Spec": {
                        "Name": "app",
                        "Labels": {
                            "unifi-dns.enable": "true",
                            "unifi-dns.source": (
                                "bad_host.home.prettybaked.com "
                                "-bad.home.prettybaked.com "
                                "outside.example.net "
                                "*.home.prettybaked.com"
                            ),
                        },
                    }
                }
            ],
            ["home.prettybaked.com"],
        )

        self.assertEqual(plan.desired, {})
        self.assertEqual(
            [(ignored.host, ignored.reason) for ignored in plan.ignored],
            [
                ("bad_host.home.prettybaked.com", "invalid hostname"),
                ("-bad.home.prettybaked.com", "invalid hostname"),
                ("outside.example.net", "outside allowed zones"),
                ("*.home.prettybaked.com", "wildcard source"),
            ],
        )

    def test_valid_hostname_contract(self):
        self.assertTrue(valid_hostname("app.home.prettybaked.com"))
        self.assertTrue(valid_hostname("xn--example.home.prettybaked.com"))
        self.assertFalse(valid_hostname("bad_host.home.prettybaked.com"))
        self.assertFalse(valid_hostname("-bad.home.prettybaked.com"))
        self.assertFalse(valid_hostname("bad-.home.prettybaked.com"))
        self.assertFalse(valid_hostname(""))


class ReconcileTests(unittest.TestCase):
    def test_create_update_noop_and_safe_removal(self):
        api = FakeUnifi([])
        controller = Controller(api, ["home.prettybaked.com"], {})
        controller.reconcile([service("app", "Host(`app.home.prettybaked.com`)", "docker-swarm")])
        self.assertEqual(api.created, [("app.home.prettybaked.com", "docker-swarm.local")])
        self.assertEqual(
            [(claim.host, claim.service, claim.kind) for claim in controller.claims],
            [("app.home.prettybaked.com", "app", "traefik")],
        )
        controller.reconcile([service("app", "Host(`app.home.prettybaked.com`)", "new-target")])
        self.assertEqual(api.updated, [("app.home.prettybaked.com", "new-target.local")])
        controller.reconcile([])
        self.assertEqual(api.deleted, ["app.home.prettybaked.com"])

    def test_reconcile_logs_summary_counts(self):
        api = FakeUnifi([])
        controller = Controller(api, ["home.prettybaked.com"], {})

        with self.assertLogs("app.controller", level="INFO") as logs:
            controller.reconcile(
                [service("app", "Host(`app.home.prettybaked.com`)", "docker-swarm")]
            )

        messages = "\n".join(logs.output)
        self.assertIn('"action": "plan"', messages)
        self.assertIn('"services": 1', messages)
        self.assertIn('"enabled_services": 1', messages)
        self.assertIn('"skipped_services": 0', messages)
        self.assertIn('"services_with_traefik_rules": 1', messages)
        self.assertIn('"desired": 1', messages)
        self.assertIn('"unifi_records": 0', messages)
        self.assertIn('"action": "reconcile"', messages)
        self.assertIn('"owned_records": 1', messages)

    def test_controller_exposes_ignored_sources(self):
        api = FakeUnifi([])
        controller = Controller(api, ["home.prettybaked.com"], {})
        controller.reconcile(
            [
                {
                    "Spec": {
                        "Name": "app",
                        "Labels": {
                            "unifi-dns.enable": "true",
                            "unifi-dns.source": "bad_host.home.prettybaked.com",
                        },
                    }
                }
            ]
        )

        self.assertEqual(api.created, [])
        self.assertEqual(
            [(ignored.service, ignored.host, ignored.reason) for ignored in controller.ignored],
            [("app", "bad_host.home.prettybaked.com", "invalid hostname")],
        )

    def test_dry_run_skips_unifi_mutations_and_ownership_updates(self):
        api = FakeUnifi([])
        ownership = {}
        controller = Controller(api, ["home.prettybaked.com"], ownership, dry_run=True)

        controller.reconcile([service("app", "Host(`app.home.prettybaked.com`)", "docker-swarm")])

        self.assertEqual(api.created, [])
        self.assertEqual(api.updated, [])
        self.assertEqual(api.deleted, [])
        self.assertEqual(ownership, {})
        self.assertEqual(controller.ownership, {})
        self.assertEqual(controller.plan.desired, {"app.home.prettybaked.com": "docker-swarm"})

    def test_dry_run_still_applies_when_enable_label_is_not_required(self):
        api = FakeUnifi([])
        ownership = {}
        controller = Controller(
            api,
            ["home.prettybaked.com"],
            ownership,
            dry_run=True,
            require_enable_label=False,
        )

        controller.reconcile(
            [
                {
                    "Spec": {
                        "Name": "app",
                        "Labels": {
                            "traefik.http.routers.app.rule": "Host(`app.home.prettybaked.com`)",
                        },
                    }
                }
            ]
        )

        self.assertEqual(api.created, [])
        self.assertEqual(ownership, {})
        self.assertEqual(controller.plan.desired, {"app.home.prettybaked.com": "docker-swarm"})

    def test_preserves_unowned_records_and_api_failure(self):
        api = FakeUnifi(
            [{"key": "manual.home.prettybaked.com", "value": "manual.local"}], fail_create=True
        )
        controller = Controller(api, ["home.prettybaked.com"], {})
        with self.assertRaises(RuntimeError):
            controller.reconcile(
                [service("new", "Host(`new.home.prettybaked.com`)", "docker-swarm")]
            )
        controller.reconcile([])
        self.assertEqual(api.deleted, [])

    def test_service_update_and_removal_converge(self):
        api = FakeUnifi([])
        controller = Controller(api, ["home.prettybaked.com"], {})
        # These snapshots model Docker create, service-update, and service-remove events.
        controller.reconcile([service("app", "Host(`old.home.prettybaked.com`)", "docker-swarm")])
        controller.reconcile([service("app", "Host(`new.home.prettybaked.com`)", "edge")])
        controller.reconcile([])
        self.assertEqual(
            api.created,
            [
                ("old.home.prettybaked.com", "docker-swarm.local"),
                ("new.home.prettybaked.com", "edge.local"),
            ],
        )
        self.assertEqual(api.deleted, ["old.home.prettybaked.com", "new.home.prettybaked.com"])


def service(name, rule, target):
    return {
        "Spec": {
            "Name": name,
            "Labels": {
                "unifi-dns.enable": "true",
                "unifi-dns.target": target,
                "traefik.http.routers.app.rule": rule,
            },
        }
    }


class FakeUnifi:
    def __init__(self, records, fail_create=False):
        self.records, self.fail_create = records, fail_create
        self.created, self.updated, self.deleted = [], [], []

    def list(self):
        return self.records

    def create(self, host, target):
        if self.fail_create:
            raise RuntimeError("API unavailable")
        self.created.append((host, target))
        self.records.append({"key": host, "value": target})

    def update(self, host, target):
        self.updated.append((host, target))

    def delete(self, host):
        self.deleted.append(host)


if __name__ == "__main__":
    unittest.main()
