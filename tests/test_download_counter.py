from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "ops" / "miaomiao-download-counter.py"
SPEC = importlib.util.spec_from_file_location("miaomiao_download_counter", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
counter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = counter
SPEC.loader.exec_module(counter)


class DownloadCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        counter.DOWNLOAD_ROOT = root.resolve()
        counter.STATE_DIR = root / "state"
        counter.STATE_FILE = counter.STATE_DIR / "counts.json"
        counter.COUNTS = {}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_only_existing_release_files(self) -> None:
        package = counter.DOWNLOAD_ROOT / "Miaomiao-7.24.6-windows-x64.zip"
        package.write_bytes(b"release")

        self.assertTrue(counter.valid_download(package.name))
        self.assertFalse(counter.valid_download("../" + package.name))
        self.assertFalse(counter.valid_download("index.html"))
        self.assertFalse(counter.valid_download("missing.zip"))

    def test_persists_counts_atomically(self) -> None:
        counter.COUNTS = {"miaomiao_2.3.4_universal.apk": 3}
        counter.persist_state()

        self.assertEqual(
            json.loads(counter.STATE_FILE.read_text(encoding="utf-8")),
            counter.COUNTS,
        )
        self.assertFalse(counter.STATE_FILE.with_suffix(".tmp").exists())

    def test_stats_endpoint_ignores_cache_busting_query(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), counter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", "/stats?v=4")
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["total"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
