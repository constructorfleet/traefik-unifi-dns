import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.state_store import JsonStateStore


class JsonStateStoreTests(unittest.TestCase):
    def test_loads_legacy_flat_ownership_state(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"app.home": "docker-swarm.local"}))
            store = JsonStateStore(path)

            self.assertEqual(store.load(), {"app.home": "docker-swarm.local"})
            self.assertEqual(store.load_manual_metadata(), {})

    def test_persists_ownership_and_manual_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = JsonStateStore(path)

            store.save(
                {"app.home": "docker-swarm.local"},
                {"old.home": {"stack": "media", "service": "requests"}},
            )

            self.assertEqual(store.load(), {"app.home": "docker-swarm.local"})
            self.assertEqual(
                store.load_manual_metadata(),
                {"old.home": {"stack": "media", "service": "requests"}},
            )


if __name__ == "__main__":
    unittest.main()
