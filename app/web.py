"""HTTP endpoints for health checks, metrics, and the controller dashboard."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .dashboard import render_dashboard


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
        self._send_html(
            render_dashboard(
                self.server.controller.ownership,
                self.server.controller.conflicts,
                self.server.controller.last_error,
            )
        )

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
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(metrics.encode())

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
