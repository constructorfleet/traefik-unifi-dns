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

    def test_requests_use_configured_ssl_verification(self):
        with client_with_key(verify_ssl=False) as client:
            with patch("app.unifi_client.requests.get", return_value=FakeResponse([])) as get:
                client.list()
            with patch("app.unifi_client.requests.post", return_value=FakeResponse({})) as post:
                client.create("app.home", "docker-swarm.local")
            with patch("app.unifi_client.requests.put", return_value=FakeResponse({})) as put:
                client.update("app.home", "edge.local")
            with patch("app.unifi_client.requests.delete", return_value=FakeResponse({})) as delete:
                client.delete("app.home")

        self.assertFalse(get.call_args.kwargs["verify"])
        self.assertFalse(post.call_args.kwargs["verify"])
        self.assertFalse(put.call_args.kwargs["verify"])
        self.assertFalse(delete.call_args.kwargs["verify"])

    def test_list_accepts_data_wrapped_response(self):
        with (
            client_with_key() as client,
            patch(
                "app.unifi_client.requests.get",
                return_value=FakeResponse({"data": [{"key": "app"}]}),
            ),
        ):
            self.assertEqual(client.list(), [{"key": "app"}])


def client_with_key(verify_ssl=True):
    return ClientContext(verify_ssl)


class ClientContext:
    def __init__(self, verify_ssl=True):
        self.verify_ssl = verify_ssl

    def __enter__(self):
        self.temp_dir = TemporaryDirectory()
        path = Path(self.temp_dir.name) / "api-key"
        path.write_text("secret")
        return UnifiStaticDnsClient("https://unifi.local", path, self.verify_ssl)

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
