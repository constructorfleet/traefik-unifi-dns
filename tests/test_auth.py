import json
import unittest
from base64 import urlsafe_b64encode
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.auth import OidcAuthenticator
from app.config import OidcSettings


class OidcAuthenticatorTests(unittest.TestCase):
    def test_authorization_url_uses_discovery_and_signed_state_cookie(self):
        auth = OidcAuthenticator(oidc_settings())

        with patch("app.auth.requests.get") as get:
            get.return_value = FakeResponse(
                {
                    "authorization_endpoint": "https://idp.example.com/auth",
                    "token_endpoint": "https://idp.example.com/token",
                    "userinfo_endpoint": "https://idp.example.com/userinfo",
                }
            )
            url, state_cookie = auth.authorization_url("https://dns.example.com/oidc/callback")

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        state = auth.unsign(state_cookie)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "idp.example.com")
        self.assertEqual(parsed.path, "/auth")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["unifi-dns"])
        self.assertEqual(query["redirect_uri"], ["https://dns.example.com/oidc/callback"])
        self.assertEqual(query["scope"], ["openid email profile groups"])
        self.assertEqual(query["state"], [state["state"]])
        self.assertIn("nonce", state)

    def test_callback_exchanges_code_checks_groups_and_signs_session(self):
        auth = OidcAuthenticator(oidc_settings(allowed_groups=("dns-admins",)))
        state_cookie = auth.sign({"state": "state-1", "nonce": "nonce-1"})

        with patch("app.auth.requests.get") as get, patch("app.auth.requests.post") as post:
            get.side_effect = [
                FakeResponse(
                    {
                        "authorization_endpoint": "https://idp.example.com/auth",
                        "token_endpoint": "https://idp.example.com/token",
                        "userinfo_endpoint": "https://idp.example.com/userinfo",
                    }
                ),
                FakeResponse(
                    {
                        "sub": "user-1",
                        "email": "user@example.com",
                        "name": "User One",
                        "groups": ["dns-admins"],
                    }
                ),
            ]
            post.return_value = FakeResponse({"access_token": "access-token"})

            session_cookie = auth.callback(
                "code-1",
                "state-1",
                state_cookie,
                "https://dns.example.com/oidc/callback",
            )

        user = auth.user(session_cookie)
        self.assertEqual(user.subject, "user-1")
        self.assertEqual(user.email, "user@example.com")
        self.assertEqual(user.name, "User One")
        self.assertEqual(user.groups, ("dns-admins",))
        self.assertEqual(post.call_args.kwargs["data"]["client_secret"], "secret")
        self.assertEqual(
            get.call_args.kwargs["headers"],
            {"Authorization": "Bearer access-token"},
        )

    def test_callback_rejects_invalid_state(self):
        auth = OidcAuthenticator(oidc_settings())

        with self.assertRaisesRegex(ValueError, "invalid OIDC state"):
            auth.callback("code-1", "state-1", "", "https://dns.example.com/oidc/callback")

    def test_callback_rejects_missing_allowed_group(self):
        auth = OidcAuthenticator(oidc_settings(allowed_groups=("dns-admins",)))
        state_cookie = auth.sign({"state": "state-1", "nonce": "nonce-1"})

        with patch("app.auth.requests.get") as get, patch("app.auth.requests.post") as post:
            get.side_effect = [
                FakeResponse(
                    {
                        "authorization_endpoint": "https://idp.example.com/auth",
                        "token_endpoint": "https://idp.example.com/token",
                        "userinfo_endpoint": "https://idp.example.com/userinfo",
                    }
                ),
                FakeResponse(
                    {
                        "sub": "user-1",
                        "email": "user@example.com",
                        "groups": ["read-only"],
                    }
                ),
            ]
            post.return_value = FakeResponse({"access_token": "access-token"})

            with self.assertRaisesRegex(ValueError, "allowed OIDC group"):
                auth.callback(
                    "code-1",
                    "state-1",
                    state_cookie,
                    "https://dns.example.com/oidc/callback",
                )

    def test_can_use_id_token_claims_when_userinfo_is_unavailable(self):
        auth = OidcAuthenticator(oidc_settings(groups_claim="roles"))
        state_cookie = auth.sign({"state": "state-1", "nonce": "nonce-1"})
        id_token = unsigned_jwt({"sub": "user-1", "roles": "admin"})

        with patch("app.auth.requests.get") as get, patch("app.auth.requests.post") as post:
            get.return_value = FakeResponse(
                {
                    "authorization_endpoint": "https://idp.example.com/auth",
                    "token_endpoint": "https://idp.example.com/token",
                    "userinfo_endpoint": "https://idp.example.com/userinfo",
                }
            )
            post.return_value = FakeResponse({"id_token": id_token})

            session_cookie = auth.callback(
                "code-1",
                "state-1",
                state_cookie,
                "https://dns.example.com/oidc/callback",
            )

        self.assertEqual(auth.user(session_cookie).groups, ("admin",))


def oidc_settings(**overrides):
    values = {
        "enabled": True,
        "discovery_url": "https://idp.example.com/.well-known/openid-configuration",
        "client_id": "unifi-dns",
        "client_secret": "secret",
        "redirect_uri": "",
        "scopes": ("openid", "email", "profile", "groups"),
        "allowed_groups": (),
        "groups_claim": "groups",
        "cookie_secret": "cookie-secret",
        "cookie_secure": True,
    }
    values.update(overrides)
    return OidcSettings(**values)


def unsigned_jwt(payload):
    header = urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}."


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


if __name__ == "__main__":
    unittest.main()
