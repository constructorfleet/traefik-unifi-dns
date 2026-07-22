import http.client
import threading
import unittest

from app.web import DashboardHttpServer


class WebEndpointTests(unittest.TestCase):
    def test_health_ready_metrics_and_dashboard_routes(self):
        controller = FakeController()
        server = DashboardHttpServer(("127.0.0.1", 0), controller)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertResponse(server, "/healthz", 200, b'{"ok": true}')
            self.assertResponse(server, "/readyz", 200, b'{"ready": true}')
            self.assertResponse(server, "/metrics", 200, b"unifi_dns_traefik_owned_records 1\n")
            self.assertResponse(server, "/metrics", 200, b"unifi_dns_traefik_dry_run 0\n")
            self.assertResponse(server, "/", 200, b"app.home.prettybaked.com")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def assertResponse(self, server, path, status, expected_body_fragment):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

        self.assertEqual(response.status, status)
        self.assertIn(expected_body_fragment, body)


class FakeController:
    ownership = {"app.home.prettybaked.com": "docker-swarm.local"}
    conflicts = {"dup.home.prettybaked.com"}
    ignored = ()
    claims = ()
    dry_run = False
    last_error = None
    last_reconcile = 1


if __name__ == "__main__":
    unittest.main()
