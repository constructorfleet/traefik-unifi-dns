import unittest

from app.runtime import ReconcileWorker


class ReconcileWorkerTests(unittest.TestCase):
    def test_reconcile_once_logs_fetched_service_count(self):
        worker = ReconcileWorker(
            controller=FakeController(),
            docker=FakeDocker([{"ID": "service-1"}]),
            state_store=FakeStateStore(),
            reconcile_interval_seconds=300,
        )

        with self.assertLogs("app.runtime", level="INFO") as logs:
            worker.reconcile_once()

        self.assertIn('"action": "docker_services"', "\n".join(logs.output))
        self.assertIn('"services": 1', "\n".join(logs.output))


class FakeController:
    ownership = {}

    def reconcile(self, services):
        self.services = services


class FakeDocker:
    def __init__(self, services):
        self.services = services

    def list_services(self):
        return self.services


class FakeStateStore:
    def save(self, ownership):
        self.ownership = ownership


if __name__ == "__main__":
    unittest.main()
