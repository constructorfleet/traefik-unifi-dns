import unittest

from app.dashboard import dashboard_state, render_dashboard
from app.traefik import IgnoredSource, SourceClaim


class DashboardTests(unittest.TestCase):
    def test_renders_reactive_dashboard_shell(self):
        html = render_dashboard()

        self.assertIn("new EventSource", html)
        self.assertIn('addEventListener("state"', html)
        self.assertIn("/events", html)
        self.assertIn("stack-filter", html)
        self.assertIn("service-filter", html)
        self.assertIn("url-filter", html)
        self.assertIn('data-tab="target-cnames-panel"', html)
        self.assertIn("deleteStaleCname", html)
        self.assertIn("addCname", html)
        self.assertIn("editCnameMetadata", html)
        self.assertIn("add-cname-form", html)
        self.assertIn('action:"record-actions"', html)
        self.assertIn("showPanel", html)
        self.assertIn("owned-records", html)
        self.assertIn("Source Claims", html)

    def test_dashboard_state_serializes_controller(self):
        state = dashboard_state(FakeController())

        self.assertEqual(state["dry_run"], True)
        self.assertEqual(state["counts"]["owned"], 1)
        self.assertEqual(
            state["owned_records"],
            [
                {
                    "hostname": "app.home",
                    "target": "edge.local",
                    "service": "app",
                    "stack": "nginx",
                }
            ],
        )
        self.assertEqual(state["conflicts"], ["dup.home"])
        self.assertEqual(state["ignored"][0]["stack"], "nginx")
        self.assertEqual(state["ignored"][0]["reason"], "invalid")
        self.assertEqual(state["claims"][0]["stack"], "nginx")
        self.assertEqual(state["claims"][0]["type"], "traefik")
        self.assertEqual(state["counts"]["unifi_target_records"], 2)
        self.assertEqual(state["counts"]["stale_unifi_target_records"], 0)
        self.assertEqual(
            state["unifi_target_records"],
            [
                {
                    "hostname": "app.home",
                    "target": "edge.local",
                    "status": "current",
                    "stack": "nginx",
                    "service": "app",
                },
                {
                    "hostname": "old.home",
                    "target": "edge.local",
                    "status": "manual",
                    "stack": "manualstack",
                    "service": "manualsvc",
                },
            ],
        )


class FakeController:
    ownership = {"app.home": "edge.local"}
    conflicts = {"dup.home"}
    ignored = (IgnoredSource("app", "nginx", "unifi-dns.source", "bad.home", "invalid"),)
    claims = (
        SourceClaim(
            host="app.home",
            target="edge",
            service="app",
            stack="nginx",
            label="traefik.http.routers.app.rule",
            kind="traefik",
        ),
    )
    dry_run = True
    last_error = None
    last_reconcile = 123.0
    default_target = "docker-swarm"
    localdomain = "local"
    always_show_delete = True
    manual_metadata = {"old.home": {"stack": "manualstack", "service": "manualsvc"}}
    unifi_records = (
        {"key": "app.home", "value": "edge.local", "type": "cname"},
        {"key": "old.home", "value": "edge.local", "type": "cname"},
        {"key": "txt.home", "value": "edge.local", "type": "txt"},
        {"key": "other.home", "value": "other.local", "type": "cname"},
    )

    class plan:
        desired = {"app.home": "edge", "old-reference.home": "edge"}
        skipped_claims = (
            SourceClaim(
                host="old.home",
                target="edge",
                service="old",
                stack="oldstack",
                label="traefik.http.routers.old.rule",
                kind="traefik",
            ),
        )

    def target_domains(self):
        return {"edge.local", "docker-swarm.local"}


if __name__ == "__main__":
    unittest.main()
