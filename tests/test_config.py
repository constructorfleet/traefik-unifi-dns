import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_normalizes_valid_settings(self):
        settings = Settings.from_env(
            {
                "UNIFI_URL": " https://unifi.local ",
                "ALLOWED_ZONES": "Home.PrettyBaked.com.,home.constructorfleet.stream",
                "DEFAULT_TARGET": "Edge",
                "CNAME_LOCALDOMAIN": "Lan.",
                "DRY_RUN": "yes",
                "REQUIRE_UNIFI_DNS_ENABLE": "false",
                "ALWAYS_SHOW_DELETE": "true",
                "UNIFI_VERIFY_SSL": "false",
                "RECONCILE_INTERVAL_SECONDS": "60",
                "PORT": "8081",
                "LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(
            settings.allowed_zones,
            ("home.prettybaked.com", "home.constructorfleet.stream"),
        )
        self.assertEqual(settings.default_target, "edge")
        self.assertEqual(settings.cname_localdomain, "lan")
        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.require_unifi_dns_enable)
        self.assertTrue(settings.always_show_delete)
        self.assertFalse(settings.unifi_verify_ssl)
        self.assertEqual(settings.log_level, "DEBUG")

    def test_rejects_invalid_dns_and_target_values(self):
        invalid_envs = [
            {"ALLOWED_ZONES": "bad_zone.example.com"},
            {"DEFAULT_TARGET": "bad_target"},
            {"CNAME_LOCALDOMAIN": "-bad"},
        ]

        for env in invalid_envs:
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env({"UNIFI_URL": "https://unifi.local", **env})

    def test_rejects_invalid_boolean_interval_port_and_log_level(self):
        invalid_envs = [
            {"DRY_RUN": "maybe"},
            {"UNIFI_VERIFY_SSL": "sometimes"},
            {"ALWAYS_SHOW_DELETE": "occasionally"},
            {"OIDC_ENABLED": "sure"},
            {"OIDC_COOKIE_SECURE": "nah"},
            {"RECONCILE_INTERVAL_SECONDS": "0"},
            {"RECONCILE_INTERVAL_SECONDS": "abc"},
            {"PORT": "0"},
            {"PORT": "65536"},
            {"LOG_LEVEL": "verbose"},
        ]

        for env in invalid_envs:
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env(
                    {
                        "UNIFI_URL": "https://unifi.local",
                        "ALLOWED_ZONES": "home.prettybaked.com",
                        **env,
                    }
                )

    def test_reads_settings_from_file_env_suffixes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            unifi_url_file = root / "unifi-url"
            zones_file = root / "allowed-zones"
            dry_run_file = root / "dry-run"
            unifi_url_file.write_text(" https://unifi.local\n")
            zones_file.write_text("home.prettybaked.com,home.constructorfleet.stream\n")
            dry_run_file.write_text("true\n")

            settings = Settings.from_env(
                {
                    "UNIFI_URL_FILE": str(unifi_url_file),
                    "ALLOWED_ZONES_FILE": str(zones_file),
                    "DRY_RUN_FILE": str(dry_run_file),
                }
            )

        self.assertEqual(settings.unifi_url, "https://unifi.local")
        self.assertEqual(
            settings.allowed_zones,
            ("home.prettybaked.com", "home.constructorfleet.stream"),
        )
        self.assertTrue(settings.dry_run)

    def test_rejects_env_value_and_file_suffix_together(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "unifi-url"
            path.write_text("https://from-file.local")

            with self.assertRaises(ValueError):
                Settings.from_env(
                    {
                        "UNIFI_URL": "https://inline.local",
                        "UNIFI_URL_FILE": str(path),
                        "ALLOWED_ZONES": "home.prettybaked.com",
                    }
                )

    def test_rejects_missing_file_env_suffix_path(self):
        with self.assertRaises(ValueError):
            Settings.from_env(
                {
                    "UNIFI_URL_FILE": "/missing/nope",
                    "ALLOWED_ZONES": "home.prettybaked.com",
                }
            )

    def test_parses_oidc_settings(self):
        settings = Settings.from_env(
            {
                "UNIFI_URL": "https://unifi.local",
                "ALLOWED_ZONES": "home.prettybaked.com",
                "OIDC_ENABLED": "true",
                "OIDC_DISCOVERY_URL": "https://idp.example.com/.well-known/openid-configuration",
                "OIDC_CLIENT_ID": "unifi-dns",
                "OIDC_CLIENT_SECRET": "secret",
                "OIDC_REDIRECT_URI": "https://dns.example.com/oidc/callback",
                "OIDC_SCOPES": "openid email profile groups",
                "OIDC_ALLOWED_GROUPS": "admins, dns-ops ",
                "OIDC_GROUPS_CLAIM": "roles",
                "OIDC_COOKIE_SECRET": "cookie-secret",
                "OIDC_COOKIE_SECURE": "false",
            }
        )

        self.assertTrue(settings.oidc.enabled)
        self.assertEqual(
            settings.oidc.discovery_url,
            "https://idp.example.com/.well-known/openid-configuration",
        )
        self.assertEqual(settings.oidc.client_id, "unifi-dns")
        self.assertEqual(settings.oidc.client_secret, "secret")
        self.assertEqual(settings.oidc.redirect_uri, "https://dns.example.com/oidc/callback")
        self.assertEqual(settings.oidc.scopes, ("openid", "email", "profile", "groups"))
        self.assertEqual(settings.oidc.allowed_groups, ("admins", "dns-ops"))
        self.assertEqual(settings.oidc.groups_claim, "roles")
        self.assertEqual(settings.oidc.cookie_secret, "cookie-secret")
        self.assertFalse(settings.oidc.cookie_secure)

    def test_rejects_incomplete_oidc_settings_when_enabled(self):
        required = [
            "OIDC_DISCOVERY_URL",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "OIDC_COOKIE_SECRET",
        ]
        base = {
            "UNIFI_URL": "https://unifi.local",
            "ALLOWED_ZONES": "home.prettybaked.com",
            "OIDC_ENABLED": "true",
            "OIDC_DISCOVERY_URL": "https://idp.example.com/.well-known/openid-configuration",
            "OIDC_CLIENT_ID": "unifi-dns",
            "OIDC_CLIENT_SECRET": "secret",
            "OIDC_COOKIE_SECRET": "cookie-secret",
        }

        for missing in required:
            env = dict(base)
            env[missing] = ""
            with (
                self.subTest(missing=missing),
                self.assertRaisesRegex(
                    ValueError,
                    f"{missing} is required",
                ),
            ):
                Settings.from_env(env)

    def test_rejects_oidc_scopes_without_openid(self):
        with self.assertRaisesRegex(ValueError, "OIDC_SCOPES must include openid"):
            Settings.from_env(
                {
                    "UNIFI_URL": "https://unifi.local",
                    "ALLOWED_ZONES": "home.prettybaked.com",
                    "OIDC_ENABLED": "true",
                    "OIDC_DISCOVERY_URL": "https://idp.example.com/.well-known/openid-configuration",
                    "OIDC_CLIENT_ID": "unifi-dns",
                    "OIDC_CLIENT_SECRET": "secret",
                    "OIDC_COOKIE_SECRET": "cookie-secret",
                    "OIDC_SCOPES": "email profile",
                }
            )


if __name__ == "__main__":
    unittest.main()
