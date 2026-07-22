import unittest

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


if __name__ == "__main__":
    unittest.main()
