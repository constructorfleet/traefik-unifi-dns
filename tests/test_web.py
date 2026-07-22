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
            self.assertResponse(server, "/", 200, b"new EventSource")
            self.assertResponse(server, "/api/state", 200, b'"owned_records"')
            self.assertResponse(server, "/api/state", 200, b"app.home.prettybaked.com")
            self.assertEventStream(server)
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

    def test_metrics_route_exposes_prometheus_gauges(self):
        controller = FakeController()
        server = DashboardHttpServer(("127.0.0.1", 0), controller)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            connection.request("GET", "/metrics")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.getheader("Content-Type"),
            "text/plain; version=0.0.4; charset=utf-8",
        )
        self.assertIn(b"# TYPE unifi_dns_traefik_ready gauge\n", body)
        self.assertIn(b"unifi_dns_traefik_ready 1\n", body)
        self.assertIn(b"unifi_dns_traefik_owned_records 1\n", body)
        self.assertIn(b"unifi_dns_traefik_conflicts 1\n", body)
        self.assertIn(b"unifi_dns_traefik_claims 0\n", body)
        self.assertIn(b"unifi_dns_traefik_stale_unifi_target_cnames 0\n", body)
        self.assertIn(b"unifi_dns_traefik_dry_run 0\n", body)

    def assertEventStream(self, server):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            connection.request("GET", "/events")
            response = connection.getresponse()
            retry = response.fp.readline()
            event = response.fp.readline()
            data = response.fp.readline()
        finally:
            connection.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(retry, b"retry: 3000\n")
        self.assertEqual(event, b"event: state\n")
        self.assertIn(b'"owned_records"', data)

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

    def test_add_cname_route_delegates_to_controller(self):
        controller = FakeController()
        state_store = FakeStateStore()
        server = DashboardHttpServer(("127.0.0.1", 0), controller, state_store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = self.request(
                server,
                "POST",
                "/api/cname",
                json.dumps({"hostname": "manual.home.prettybaked.com"}).encode(),
            )
            invalid_status, invalid_body = self.request(
                server,
                "POST",
                "/api/cname",
                json.dumps({"hostname": "manual.example.net"}).encode(),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"result": "created"})
        self.assertEqual(controller.added_cnames, [("manual.home.prettybaked.com", None)])
        self.assertEqual(state_store.saved[-1][0], controller.ownership)
        self.assertEqual(invalid_status, 400)
        self.assertEqual(json.loads(invalid_body), {"error": "outside allowed zones"})

    def test_edit_cname_metadata_route_delegates_and_persists(self):
        controller = FakeController()
        state_store = FakeStateStore()
        server = DashboardHttpServer(("127.0.0.1", 0), controller, state_store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = self.request(
                server,
                "POST",
                "/api/cname-metadata",
                json.dumps(
                    {
                        "hostname": "old.home.prettybaked.com",
                        "stack": "media",
                        "service": "requests",
                    }
                ).encode(),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"result": "saved"})
        self.assertEqual(
            controller.edited_metadata,
            [("old.home.prettybaked.com", "media", "requests")],
        )
        self.assertEqual(state_store.saved[-1][1], controller.manual_metadata)

    def test_oidc_protects_dashboard_and_api_routes(self):
        controller = FakeController()
        authenticator = FakeAuthenticator()
        server = DashboardHttpServer(
            ("127.0.0.1", 0),
            controller,
            authenticator=authenticator,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            dashboard_status, dashboard_headers, dashboard_body = self.request_with_headers(
                server,
                "GET",
                "/",
            )
            api_status, _api_headers, api_body = self.request_with_headers(
                server,
                "GET",
                "/api/state",
            )
            auth_status, _auth_headers, auth_body = self.request_with_headers(
                server,
                "GET",
                "/",
                headers={"Cookie": "oidc_session=session-cookie"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(dashboard_status, 302)
        self.assertEqual(dashboard_headers["Location"], "/login")
        self.assertEqual(dashboard_body, b"")
        self.assertEqual(api_status, 401)
        self.assertEqual(json.loads(api_body), {"error": "authentication required"})
        self.assertEqual(auth_status, 200)
        self.assertIn(b"UniFi DNS Traefik", auth_body)

    def test_oidc_login_callback_and_logout_routes_manage_cookies(self):
        controller = FakeController()
        authenticator = FakeAuthenticator()
        server = DashboardHttpServer(
            ("127.0.0.1", 0),
            controller,
            authenticator=authenticator,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            login_status, login_headers, _login_body = self.request_with_headers(
                server,
                "GET",
                "/login",
            )
            callback_status, callback_headers, _callback_body = self.request_with_headers(
                server,
                "GET",
                "/oidc/callback?code=code-1&state=state-1",
                headers={"Cookie": "oidc_state=state-cookie"},
            )
            logout_status, logout_headers, _logout_body = self.request_with_headers(
                server,
                "GET",
                "/logout",
                headers={"Cookie": "oidc_session=session-cookie"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(login_status, 302)
        self.assertEqual(login_headers["Location"], "https://idp.example.com/auth")
        self.assertIn("oidc_state=state-cookie", login_headers["Set-Cookie"])
        self.assertEqual(callback_status, 302)
        self.assertEqual(callback_headers["Location"], "/")
        self.assertIn("oidc_session=session-cookie", callback_headers["Set-Cookie"])
        self.assertEqual(
            authenticator.callbacks,
            [
                (
                    "code-1",
                    "state-1",
                    "state-cookie",
                    f"http://127.0.0.1:{server.server_address[1]}/oidc/callback",
                )
            ],
        )
        self.assertEqual(logout_status, 302)
        self.assertEqual(logout_headers["Location"], "/")
        self.assertIn(
            "oidc_session=; Path=/; SameSite=Lax; Max-Age=0", logout_headers["Set-Cookie"]
        )

    def request(self, server, method, path, body=None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            headers = {"Content-Type": "application/json"} if body else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

        return response.status, body

    def request_with_headers(self, server, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            request_headers = dict(headers or {})
            if body:
                request_headers.setdefault("Content-Type", "application/json")
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            response_headers = {}
            for name, value in response.getheaders():
                response_headers[name] = (
                    f"{response_headers[name]}\n{value}" if name in response_headers else value
                )
        finally:
            connection.close()

        return response.status, response_headers, body


class FakeAuthenticator:
    enabled = True
    settings = type("Settings", (), {"cookie_secure": False})()

    def __init__(self):
        self.callbacks = []

    def authorization_url(self, callback_url):
        self.callback_url = callback_url
        return "https://idp.example.com/auth", "state-cookie"

    def callback(self, code, state, state_cookie, callback_url):
        self.callbacks.append((code, state, state_cookie, callback_url))
        return "session-cookie"

    def user(self, session_cookie):
        if session_cookie == "session-cookie":
            return object()
        return None


class FakeController:
    def __init__(self):
        self.ownership = {"app.home.prettybaked.com": "docker-swarm.local"}
        self.conflicts = {"dup.home.prettybaked.com"}
        self.ignored = ()
        self.claims = ()
        self.unifi_records = ()
        self.default_target = "docker-swarm"
        self.localdomain = "local"
        self.always_show_delete = False
        self.plan = type("Plan", (), {"desired": {}, "skipped_claims": ()})()
        self.manual_metadata = {}
        self.dry_run = False
        self.last_error = None
        self.last_reconcile = 1
        self.deleted_stale = []
        self.added_cnames = []
        self.edited_metadata = []

    def target_domains(self):
        return {"docker-swarm.local"}

    def delete_stale_target_cname(self, hostname):
        if hostname == "app.home.prettybaked.com":
            raise ValueError("hostname is not a stale target CNAME")
        self.deleted_stale.append(hostname)
        return "deleted"

    def add_cname(self, hostname, target=None):
        if not hostname.endswith(".home.prettybaked.com"):
            raise ValueError("outside allowed zones")
        self.added_cnames.append((hostname, target))
        return "created"

    def edit_cname_metadata(self, hostname, stack, service):
        self.manual_metadata[hostname] = {"stack": stack, "service": service}
        self.edited_metadata.append((hostname, stack, service))
        return "saved"


class FakeStateStore:
    def __init__(self):
        self.saved = []

    def save(self, ownership, manual_metadata=None):
        self.saved.append((dict(ownership), dict(manual_metadata or {})))


if __name__ == "__main__":
    unittest.main()
