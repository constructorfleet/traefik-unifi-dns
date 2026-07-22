"""HTTP endpoints for health checks, metrics, and the controller dashboard."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .dashboard import dashboard_state, render_dashboard


class DashboardHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address, controller):
        super().__init__(server_address, DashboardRequestHandler)
        self.controller = controller


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        if self.path == "/readyz":
            ready = bool(self.server.controller.last_reconcile)
            self._send_json(200 if ready else 503, {"ready": ready})
            return
        if self.path == "/metrics":
            self._send_metrics()
            return
        if self.path == "/api/state":
            self._send_json(200, dashboard_state(self.server.controller))
            return
        if self.path == "/events":
            self._send_event(dashboard_state(self.server.controller))
            return
        self._send_html(render_dashboard())

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/stale-cname":
            self._send_json(404, {"error": "not found"})
            return
        hostname = parse_qs(parsed.query).get("hostname", [""])[0].strip()
        if not hostname:
            self._send_json(400, {"error": "hostname is required"})
            return
        try:
            result = self.server.controller.delete_stale_target_cname(hostname)
        except ValueError as error:
            self._send_json(409, {"error": str(error)})
            return
        self._send_json(200, {"hostname": hostname, "result": result})

    def _send_json(self, status: int, body: dict[str, object]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def _send_metrics(self) -> None:
        controller = self.server.controller
        metrics = (
            f"unifi_dns_traefik_conflicts {len(controller.conflicts)}\n"
            f"unifi_dns_traefik_owned_records {len(controller.ownership)}\n"
            f"unifi_dns_traefik_dry_run {int(controller.dry_run)}\n"
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(metrics.encode())

    def _send_event(self, body: dict[str, object]) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"retry: 3000\n")
        self.wfile.write(b"event: state\n")
        self.wfile.write(b"data: " + data + b"\n\n")

    def _send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the server's unstructured access log."""
        del format, args


def serve(controller, port: int) -> None:
    DashboardHttpServer(("", port), controller).serve_forever()
