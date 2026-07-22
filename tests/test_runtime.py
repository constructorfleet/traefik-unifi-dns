import unittest

import requests

from app.runtime import ReconcileWorker


class ReconcileWorkerTests(unittest.TestCase):
    def test_reconcile_once_logs_fetched_service_count(self):
        state_store = FakeStateStore()
        worker = ReconcileWorker(
            controller=FakeController(),
            docker=FakeDocker([{"ID": "service-1"}]),
            state_store=state_store,
            reconcile_interval_seconds=300,
        )

        with self.assertLogs("app.runtime", level="INFO") as logs:
            worker.reconcile_once()

        self.assertIn('"action": "docker_services"', "\n".join(logs.output))
        self.assertIn('"services": 1', "\n".join(logs.output))
        self.assertEqual(
            state_store.manual_metadata,
            {"old.home": {"stack": "media", "service": "requests"}},
        )

    def test_wait_for_service_events_treats_stream_timeout_as_reconnect(self):
        response = FakeEventResponse(requests.exceptions.ConnectionError("Read timed out."))
        worker = ReconcileWorker(
            controller=FakeController(),
            docker=FakeDocker([], response),
            state_store=FakeStateStore(),
            reconcile_interval_seconds=300,
        )

        with self.assertLogs("app.runtime", level="INFO") as logs:
            worker.wait_for_service_events()

        messages = "\n".join(logs.output)
        self.assertTrue(response.closed)
        self.assertEqual(worker.docker.read_timeout_seconds, 300)
        self.assertIn('"action": "docker_events"', messages)
        self.assertIn('"result": "connected"', messages)
        self.assertIn('"result": "reconnect"', messages)


class FakeController:
    ownership = {}
    manual_metadata = {"old.home": {"stack": "media", "service": "requests"}}

    def reconcile(self, services):
        self.services = services


class FakeDocker:
    def __init__(self, services, response=None):
        self.services = services
        self.response = response

    def list_services(self):
        return self.services

    def stream_service_events(self, read_timeout_seconds=70):
        self.read_timeout_seconds = read_timeout_seconds
        return self.response or FakeEventResponse([])


class FakeEventResponse:
    def __init__(self, lines_or_error):
        self.lines_or_error = lines_or_error
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        if isinstance(self.lines_or_error, Exception):
            raise self.lines_or_error
        yield from self.lines_or_error

    def close(self):
        self.closed = True


class FakeStateStore:
    def save(self, ownership, manual_metadata=None):
        self.ownership = ownership
        self.manual_metadata = manual_metadata


if __name__ == "__main__":
    unittest.main()
