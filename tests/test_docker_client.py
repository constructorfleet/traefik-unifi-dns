import unittest

from app.docker_client import DockerClient


class DockerClientTests(unittest.TestCase):
    def test_tcp_endpoint_uses_http_base_url(self):
        client = DockerClient("tcp://docker-socket-proxy:2375")

        self.assertEqual(client.base_url, "http://docker-socket-proxy:2375/v1.41")

    def test_http_endpoint_is_preserved(self):
        client = DockerClient("http://docker-socket-proxy:2375/")

        self.assertEqual(client.base_url, "http://docker-socket-proxy:2375/v1.41")

    def test_unix_endpoint_uses_unix_socket_adapter_url(self):
        client = DockerClient("unix:///var/run/docker.sock")

        self.assertEqual(client.base_url, "http+unix://%2Fvar%2Frun%2Fdocker.sock/v1.41")


if __name__ == "__main__":
    unittest.main()
