import unittest

from app.controller import Controller
from app.traefik import desired_records, extract_hosts, normalize_host, plan_records


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


class ReconcileTests(unittest.TestCase):
    def test_create_update_noop_and_safe_removal(self):
        api = FakeUnifi([])
        controller = Controller(api, ["home.prettybaked.com"], {})
        controller.reconcile([service("app", "Host(`app.home.prettybaked.com`)", "docker-swarm")])
        self.assertEqual(api.created, [("app.home.prettybaked.com", "docker-swarm.local")])
        controller.reconcile([service("app", "Host(`app.home.prettybaked.com`)", "new-target")])
        self.assertEqual(api.updated, [("app.home.prettybaked.com", "new-target.local")])
        controller.reconcile([])
        self.assertEqual(api.deleted, ["app.home.prettybaked.com"])

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
