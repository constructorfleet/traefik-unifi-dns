"""Runtime reconciliation loop."""

from __future__ import annotations

import json
import logging
import time

from .controller import Controller
from .docker_client import DockerClient
from .state_store import JsonStateStore

LOG = logging.getLogger(__name__)


class ReconcileWorker:
    def __init__(
        self,
        controller: Controller,
        docker: DockerClient,
        state_store: JsonStateStore,
        reconcile_interval_seconds: int,
        debounce_seconds: float = 2.0,
        error_sleep_seconds: float = 5.0,
    ) -> None:
        self.controller = controller
        self.docker = docker
        self.state_store = state_store
        self.reconcile_interval_seconds = reconcile_interval_seconds
        self.debounce_seconds = debounce_seconds
        self.error_sleep_seconds = error_sleep_seconds

    def run_forever(self) -> None:
        while True:
            try:
                self.reconcile_once()
                self.wait_for_service_events()
            except Exception as error:
                self.controller.last_error = str(error)
                LOG.exception("reconciliation failed")
                time.sleep(self.error_sleep_seconds)

    def reconcile_once(self) -> None:
        services = self.docker.list_services()
        LOG.info(json.dumps({"action": "docker_services", "services": len(services)}))
        self.controller.reconcile(services)
        self.state_store.save(self.controller.ownership)
        LOG.info(
            json.dumps(
                {
                    "action": "state_save",
                    "owned_records": len(self.controller.ownership),
                }
            )
        )

    def wait_for_service_events(self) -> None:
        response = self.docker.stream_service_events()
        response.raise_for_status()
        LOG.info(
            json.dumps(
                {
                    "action": "docker_events",
                    "result": "connected",
                    "timeout_seconds": self.reconcile_interval_seconds,
                }
            )
        )
        deadline = time.monotonic() + self.reconcile_interval_seconds
        try:
            for _line in response.iter_lines():
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.debounce_seconds)
        finally:
            response.close()
