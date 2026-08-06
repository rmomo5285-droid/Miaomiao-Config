#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit


DOWNLOAD_ROOT = Path("/var/www/download").resolve()
STATE_DIR = Path("/var/lib/miaomiao-download-counter")
STATE_FILE = STATE_DIR / "counts.json"
ALLOWED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$")
ALLOWED_SUFFIXES = {".apk", ".zip", ".exe", ".dmg", ".deb", ".rpm", ".asc", ".txt"}
LOCK = threading.Lock()


def load_state() -> dict[str, int]:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        name: count
        for name, count in raw.items()
        if isinstance(name, str) and isinstance(count, int) and count >= 0
    }


COUNTS = load_state()


def persist_state() -> None:
    STATE_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(COUNTS, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o640)
    os.replace(temporary, STATE_FILE)


def valid_download(name: str) -> bool:
    if not ALLOWED_NAME.fullmatch(name) or Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        return False
    candidate = (DOWNLOAD_ROOT / name).resolve()
    return candidate.parent == DOWNLOAD_ROOT and candidate.is_file()


class Handler(BaseHTTPRequestHandler):
    server_version = "MiaomiaoDownloadCounter/1"

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/stats":
            self.send_stats()
            return
        self.send_download(count=True)

    def do_HEAD(self) -> None:
        self.send_download(count=False)

    def send_stats(self) -> None:
        with LOCK:
            files = dict(COUNTS)
        body = json.dumps(
            {
                "total": sum(files.values()),
                "files": files,
                "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_download(self, *, count: bool) -> None:
        name = self.headers.get("X-Download-File", "")
        if not valid_download(name):
            self.send_error(404)
            return
        if count:
            with LOCK:
                COUNTS[name] = COUNTS.get(name, 0) + 1
                persist_state()
        self.send_response(200)
        self.send_header("X-Accel-Redirect", f"/__miaomiao_download/{quote(name)}")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    STATE_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", 18765), Handler).serve_forever()
