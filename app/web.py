"""HTTP endpoints for health checks, metrics, and the controller dashboard."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from .dashboard import dashboard_state, render_dashboard


class DashboardHttpServer(ThreadingHTTPServer):
    controller: Any
    event_interval_seconds: float

    def __init__(
        self,
        server_address,
        controller: Any,
        event_interval_seconds: float = 3,
    ) -> None:
        super().__init__(server_address, DashboardRequestHandler)
        self.controller = controller
        self.event_interval_seconds = event_interval_seconds


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        if self.path == "/readyz":
            ready = bool(self._dashboard_server.controller.last_reconcile)
            self._send_json(200 if ready else 503, {"ready": ready})
            return
        if self.path == "/metrics":
            self._send_metrics()
            return
        if self.path == "/api/state":
            self._send_json(200, dashboard_state(self._dashboard_server.controller))
            return
        if self.path == "/events":
            self._send_events()
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
            result = self._dashboard_server.controller.delete_stale_target_cname(hostname)
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
        controller = self._dashboard_server.controller
        state = dashboard_state(controller)
        counts = cast(dict[str, int], state["counts"])
        metrics = _prometheus_metrics(
            {
                "ready": (
                    "Whether the controller has completed a successful reconcile.",
                    int(bool(controller.last_reconcile)),
                ),
                "dry_run": (
                    "Whether UniFi mutations are disabled.",
                    int(controller.dry_run),
                ),
                "last_reconcile_timestamp_seconds": (
                    "Last successful reconcile Unix timestamp.",
                    controller.last_reconcile or 0,
                ),
                "last_error": (
                    "Whether the last reconcile ended with an error.",
                    int(bool(controller.last_error)),
                ),
                "owned_records": (
                    "Controller-owned UniFi DNS records.",
                    counts["owned"],
                ),
                "claims": (
                    "Active DNS source claims parsed from labels.",
                    counts["claims"],
                ),
                "conflicts": (
                    "Hostnames claimed by multiple targets.",
                    counts["conflicts"],
                ),
                "ignored_sources": (
                    "Ignored DNS sources from invalid or disallowed labels.",
                    counts["ignored"],
                ),
                "unifi_target_cnames": (
                    "UniFi CNAME records pointing at active DNS targets.",
                    counts["unifi_target_records"],
                ),
                "stale_unifi_target_cnames": (
                    "UniFi target CNAMEs not present in the current desired plan.",
                    counts["stale_unifi_target_records"],
                ),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.end_headers()
        self.wfile.write(metrics.encode())

    def _send_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(b"retry: 3000\n")
        while True:
            try:
                data = json.dumps(dashboard_state(self._dashboard_server.controller)).encode()
                self.wfile.write(b"event: state\n")
                self.wfile.write(b"data: " + data + b"\n\n")
                self.wfile.flush()
                time.sleep(self._dashboard_server.event_interval_seconds)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    def _send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the server's unstructured access log."""
        del format, args

    @property
    def _dashboard_server(self) -> DashboardHttpServer:
        return cast(DashboardHttpServer, self.server)


def serve(controller, port: int) -> None:
    DashboardHttpServer(("", port), controller).serve_forever()


def _prometheus_metrics(metrics: dict[str, tuple[str, object]]) -> str:
    lines = []
    for suffix, (help_text, value) in metrics.items():
        name = f"unifi_dns_traefik_{suffix}"
        lines.extend(
            [
                f"# HELP {name} {help_text}",
                f"# TYPE {name} gauge",
                f"{name} {value}",
            ]
        )
    return "\n".join([*lines, ""])
