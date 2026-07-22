"""HTTP endpoints for health checks, metrics, and the controller dashboard."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from .dashboard import dashboard_state, render_dashboard


class DashboardHttpServer(ThreadingHTTPServer):
    controller: Any
    state_store: Any
    authenticator: Any
    event_interval_seconds: float

    def __init__(
        self,
        server_address,
        controller: Any,
        state_store: Any = None,
        authenticator: Any = None,
        event_interval_seconds: float = 3,
    ) -> None:
        super().__init__(server_address, DashboardRequestHandler)
        self.controller = controller
        self.state_store = state_store
        self.authenticator = authenticator
        self.event_interval_seconds = event_interval_seconds


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
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
        if parsed.path == "/login":
            self._login()
            return
        if parsed.path == "/oidc/callback":
            self._oidc_callback(parsed)
            return
        if parsed.path == "/logout":
            self._logout()
            return
        if not self._authenticated():
            self._unauthorized()
            return
        if self.path == "/api/state":
            self._send_json(200, dashboard_state(self._dashboard_server.controller))
            return
        if self.path == "/events":
            self._send_events()
            return
        self._send_html(render_dashboard())

    def do_POST(self) -> None:
        if not self._authenticated():
            self._unauthorized()
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/cname":
            try:
                payload = self._read_json()
                result = self._dashboard_server.controller.add_cname(
                    str(payload.get("hostname", "")),
                    str(payload.get("target", "")) or None,
                )
                self._save_state()
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, {"result": result})
            return
        if parsed.path == "/api/cname-metadata":
            try:
                payload = self._read_json()
                result = self._dashboard_server.controller.edit_cname_metadata(
                    str(payload.get("hostname", "")),
                    str(payload.get("stack", "")),
                    str(payload.get("service", "")),
                )
                self._save_state()
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, {"result": result})
            return
        else:
            self._send_json(404, {"error": "not found"})
            return

    def do_DELETE(self) -> None:
        if not self._authenticated():
            self._unauthorized()
            return
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
            self._save_state()
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

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

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

    def _save_state(self) -> None:
        state_store = self._dashboard_server.state_store
        if state_store is None:
            return
        controller = self._dashboard_server.controller
        state_store.save(controller.ownership, controller.manual_metadata)

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

    def _login(self) -> None:
        authenticator = self._dashboard_server.authenticator
        if authenticator is None or not authenticator.enabled:
            self._redirect("/")
            return
        url, state_cookie = authenticator.authorization_url(self._callback_url())
        self.send_response(302)
        self.send_header("Location", url)
        self._set_cookie("oidc_state", state_cookie, max_age=300, http_only=True)
        self.end_headers()

    def _oidc_callback(self, parsed) -> None:
        authenticator = self._dashboard_server.authenticator
        if authenticator is None or not authenticator.enabled:
            self._redirect("/")
            return
        query = parse_qs(parsed.query)
        try:
            session = authenticator.callback(
                query.get("code", [""])[0],
                query.get("state", [""])[0],
                self._cookie("oidc_state") or "",
                self._callback_url(),
            )
        except Exception as error:
            self._send_json(403, {"error": str(error)})
            return
        self.send_response(302)
        self.send_header("Location", "/")
        self._set_cookie("oidc_session", session, max_age=86400, http_only=True)
        self._set_cookie("oidc_state", "", max_age=0, http_only=True)
        self.end_headers()

    def _logout(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/")
        self._set_cookie("oidc_session", "", max_age=0, http_only=True)
        self.end_headers()

    def _authenticated(self) -> bool:
        authenticator = self._dashboard_server.authenticator
        if authenticator is None or not authenticator.enabled:
            return True
        return authenticator.user(self._cookie("oidc_session")) is not None

    def _unauthorized(self) -> None:
        if self.path == "/" or self.path == "":
            self._redirect("/login")
            return
        self._send_json(401, {"error": "authentication required"})

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _callback_url(self) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "http")
        host = self.headers.get("X-Forwarded-Host", self.headers.get("Host", "localhost"))
        return f"{proto}://{host}/oidc/callback"

    def _cookie(self, name: str) -> str | None:
        prefix = f"{name}="
        for cookie in self.headers.get("Cookie", "").split(";"):
            value = cookie.strip()
            if value.startswith(prefix):
                return value[len(prefix) :]
        return None

    def _set_cookie(
        self,
        name: str,
        value: str,
        max_age: int,
        http_only: bool,
    ) -> None:
        authenticator = self._dashboard_server.authenticator
        secure = bool(authenticator and authenticator.settings.cookie_secure)
        parts = [
            f"{name}={value}",
            "Path=/",
            "SameSite=Lax",
            f"Max-Age={max_age}",
        ]
        if http_only:
            parts.append("HttpOnly")
        if secure:
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the server's unstructured access log."""
        del format, args

    @property
    def _dashboard_server(self) -> DashboardHttpServer:
        return cast(DashboardHttpServer, self.server)


def serve(controller, port: int, state_store=None, authenticator=None) -> None:
    DashboardHttpServer(("", port), controller, state_store, authenticator).serve_forever()


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
