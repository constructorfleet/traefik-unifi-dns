import logging
import threading

from app.config import Settings
from app.controller import Controller
from app.docker_client import DockerClient
from app.runtime import ReconcileWorker
from app.state_store import JsonStateStore
from app.unifi_client import UnifiStaticDnsClient
from app.web import serve


def build_controller(settings: Settings, state_store: JsonStateStore) -> Controller:
    return Controller(
        UnifiStaticDnsClient(settings.unifi_url, settings.unifi_api_key_file),
        settings.allowed_zones,
        state_store.load(),
        settings.default_target,
        settings.cname_localdomain,
    )


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(message)s")

    state_store = JsonStateStore(settings.state_path)
    controller = build_controller(settings, state_store)
    worker = ReconcileWorker(
        controller,
        DockerClient(settings.docker_host),
        state_store,
        settings.reconcile_interval_seconds,
    )

    threading.Thread(target=worker.run_forever, daemon=True).start()
    serve(controller, settings.port)


if __name__ == "__main__":
    main()
