import http.client
import json
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
            self.assertResponse(server, "/", 200, b"new EventSource")
            self.assertResponse(server, "/api/state", 200, b'"owned_records"')
            self.assertResponse(server, "/api/state", 200, b"app.home.prettybaked.com")
            self.assertResponse(server, "/events", 200, b"event: state")
            self.assertResponse(server, "/events", 200, b"data: ")
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

    def test_delete_stale_cname_route_delegates_to_controller(self):
        controller = FakeController()
        server = DashboardHttpServer(("127.0.0.1", 0), controller)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = self.request(
                server,
                "DELETE",
                "/api/stale-cname?hostname=old.home.prettybaked.com",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(body),
            {"hostname": "old.home.prettybaked.com", "result": "deleted"},
        )
        self.assertEqual(controller.deleted_stale, ["old.home.prettybaked.com"])

    def test_delete_stale_cname_route_validates_hostname(self):
        controller = FakeController()
        server = DashboardHttpServer(("127.0.0.1", 0), controller)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            missing_status, missing_body = self.request(server, "DELETE", "/api/stale-cname")
            current_status, current_body = self.request(
                server,
                "DELETE",
                "/api/stale-cname?hostname=app.home.prettybaked.com",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(missing_status, 400)
        self.assertEqual(json.loads(missing_body), {"error": "hostname is required"})
        self.assertEqual(current_status, 409)
        self.assertEqual(
            json.loads(current_body),
            {"error": "hostname is not a stale target CNAME"},
        )

    def request(self, server, method, path):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

        return response.status, body


class FakeController:
    def __init__(self):
        self.ownership = {"app.home.prettybaked.com": "docker-swarm.local"}
        self.conflicts = {"dup.home.prettybaked.com"}
        self.ignored = ()
        self.claims = ()
        self.unifi_records = ()
        self.localdomain = "local"
        self.plan = type("Plan", (), {"desired": {}})()
        self.dry_run = False
        self.last_error = None
        self.last_reconcile = 1
        self.deleted_stale = []

    def delete_stale_target_cname(self, hostname):
        if hostname == "app.home.prettybaked.com":
            raise ValueError("hostname is not a stale target CNAME")
        self.deleted_stale.append(hostname)
        return "deleted"


if __name__ == "__main__":
    unittest.main()
