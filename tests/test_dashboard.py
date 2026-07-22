import unittest

from app.dashboard import render_dashboard
from app.traefik import IgnoredSource, SourceClaim


class DashboardTests(unittest.TestCase):
    def test_renders_owned_records_conflicts_and_error(self):
        html = render_dashboard(
            ownership={"app.home.prettybaked.com": "docker-swarm.local"},
            conflicts={"dup.home.prettybaked.com"},
            last_error="UniFi said <nope>",
            ignored=[
                IgnoredSource("app", "unifi-dns.source", "bad_host.home.prettybaked.com", "invalid")
            ],
            claims=[
                SourceClaim(
                    host="app.home.prettybaked.com",
                    target="docker-swarm",
                    service="app",
                    label="traefik.http.routers.app.rule",
                    kind="traefik",
                )
            ],
        )

        self.assertIn("<td>app.home.prettybaked.com</td>", html)
        self.assertIn("<td>docker-swarm.local</td>", html)
        self.assertIn("dup.home.prettybaked.com", html)
        self.assertIn("UniFi said &lt;nope&gt;", html)
        self.assertIn("bad_host.home.prettybaked.com", html)
        self.assertIn("invalid", html)
        self.assertIn("traefik.http.routers.app.rule", html)

    def test_renders_empty_state(self):
        html = render_dashboard(
            ownership={}, conflicts=set(), last_error=None, ignored=[], claims=[]
        )

        self.assertIn("No controller-owned records", html)
        self.assertIn("No ignored labels", html)
        self.assertIn("No active source claims", html)
        self.assertIn("<code>None</code>", html)


if __name__ == "__main__":
    unittest.main()
