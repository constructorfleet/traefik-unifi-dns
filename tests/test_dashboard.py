import unittest

from app.dashboard import dashboard_state, render_dashboard
from app.traefik import IgnoredSource, SourceClaim


class DashboardTests(unittest.TestCase):
    def test_renders_reactive_dashboard_shell(self):
        html = render_dashboard()

        self.assertIn("new EventSource", html)
        self.assertIn('addEventListener("state"', html)
        self.assertIn("/events", html)
        self.assertIn("owned-records", html)
        self.assertIn("Source Claims", html)

    def test_dashboard_state_serializes_controller(self):
        state = dashboard_state(FakeController())

        self.assertEqual(state["dry_run"], True)
        self.assertEqual(state["counts"]["owned"], 1)
        self.assertEqual(state["owned_records"], [{"hostname": "app.home", "target": "edge.local"}])
        self.assertEqual(state["conflicts"], ["dup.home"])
        self.assertEqual(state["ignored"][0]["reason"], "invalid")
        self.assertEqual(state["claims"][0]["type"], "traefik")


class FakeController:
    ownership = {"app.home": "edge.local"}
    conflicts = {"dup.home"}
    ignored = (IgnoredSource("app", "unifi-dns.source", "bad.home", "invalid"),)
    claims = (
        SourceClaim(
            host="app.home",
            target="edge",
            service="app",
            label="traefik.http.routers.app.rule",
            kind="traefik",
        ),
    )
    dry_run = True
    last_error = None
    last_reconcile = 123.0


if __name__ == "__main__":
    unittest.main()
