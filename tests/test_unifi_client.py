import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.unifi_client import UnifiStaticDnsClient


class UnifiStaticDnsClientTests(unittest.TestCase):
    def test_list_accepts_raw_list_response(self):
        with (
            client_with_key() as client,
            patch("app.unifi_client.requests.get", return_value=FakeResponse([{"key": "app"}])),
        ):
            self.assertEqual(client.list(), [{"key": "app"}])

    def test_list_accepts_data_wrapped_response(self):
        with (
            client_with_key() as client,
            patch(
                "app.unifi_client.requests.get",
                return_value=FakeResponse({"data": [{"key": "app"}]}),
            ),
        ):
            self.assertEqual(client.list(), [{"key": "app"}])


def client_with_key():
    return ClientContext()


class ClientContext:
    def __enter__(self):
        self.temp_dir = TemporaryDirectory()
        path = Path(self.temp_dir.name) / "api-key"
        path.write_text("secret")
        return UnifiStaticDnsClient("https://unifi.local", path)

    def __exit__(self, *args):
        self.temp_dir.cleanup()


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


if __name__ == "__main__":
    unittest.main()
