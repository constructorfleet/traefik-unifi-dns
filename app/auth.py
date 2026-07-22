"""Small OIDC authorization-code helper for the dashboard HTTP server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


@dataclass(frozen=True)
class User:
    subject: str
    email: str
    name: str
    groups: tuple[str, ...]


class OidcAuthenticator:
    def __init__(self, settings) -> None:
        self.settings = settings
        self._discovery: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def authorization_url(self, callback_url: str) -> tuple[str, str]:
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.client_id,
                "redirect_uri": self._redirect_uri(callback_url),
                "scope": " ".join(self.settings.scopes),
                "state": state,
                "nonce": nonce,
            }
        )
        return f"{self.discovery['authorization_endpoint']}?{query}", self.sign(
            {
                "state": state,
                "nonce": nonce,
                "created": int(time.time()),
            }
        )

    def callback(self, code: str, state: str, state_cookie: str, callback_url: str) -> str:
        expected = self.unsign(state_cookie)
        if not expected or expected.get("state") != state:
            raise ValueError("invalid OIDC state")
        token = self._exchange_code(code, callback_url)
        claims = self._userinfo(token)
        groups = self._groups(claims)
        if self.settings.allowed_groups and not set(groups).intersection(
            self.settings.allowed_groups
        ):
            raise ValueError("user is not in an allowed OIDC group")
        return self.sign(
            {
                "sub": str(claims.get("sub", "")),
                "email": str(claims.get("email", "")),
                "name": str(claims.get("name", "")),
                "groups": groups,
                "created": int(time.time()),
            }
        )

    def user(self, session_cookie: str | None) -> User | None:
        if not session_cookie:
            return None
        claims = self.unsign(session_cookie)
        if not claims:
            return None
        return User(
            subject=str(claims.get("sub", "")),
            email=str(claims.get("email", "")),
            name=str(claims.get("name", "")),
            groups=tuple(str(group) for group in claims.get("groups", [])),
        )

    @property
    def discovery(self) -> dict[str, Any]:
        if self._discovery is None:
            response = requests.get(self.settings.discovery_url, timeout=15)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("OIDC discovery response must be a JSON object")
            self._discovery = body
        return self._discovery

    def sign(self, payload: dict[str, Any]) -> str:
        body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _b64(
            hmac.new(self.settings.cookie_secret.encode(), body.encode(), hashlib.sha256).digest()
        )
        return f"{body}.{signature}"

    def unsign(self, value: str) -> dict[str, Any] | None:
        try:
            body, signature = value.split(".", 1)
        except ValueError:
            return None
        expected = _b64(
            hmac.new(self.settings.cookie_secret.encode(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = json.loads(_unb64(body))
        return decoded if isinstance(decoded, dict) else None

    def _exchange_code(self, code: str, callback_url: str) -> dict[str, Any]:
        response = requests.post(
            self.discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri(callback_url),
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("OIDC token response must be a JSON object")
        return body

    def _userinfo(self, token: dict[str, Any]) -> dict[str, Any]:
        access_token = token.get("access_token")
        if not access_token:
            return _jwt_payload(str(token.get("id_token", "")))
        response = requests.get(
            self.discovery["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("OIDC userinfo response must be a JSON object")
        return body

    def _groups(self, claims: dict[str, Any]) -> list[str]:
        raw = claims.get(self.settings.groups_claim, [])
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list | tuple):
            return [str(group) for group in raw]
        return []

    def _redirect_uri(self, callback_url: str) -> str:
        return self.settings.redirect_uri or callback_url


def _jwt_payload(token: str) -> dict[str, Any]:
    try:
        _header, payload, _signature = token.split(".", 2)
        body = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
