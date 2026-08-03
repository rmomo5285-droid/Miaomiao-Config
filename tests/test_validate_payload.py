from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "validate-payload.py"
SPEC = importlib.util.spec_from_file_location("validate_payload", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class PayloadValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
        self.payload = {
            "schema": 1,
            "version": 1,
            "issuedAt": "2026-01-01T00:00:00Z",
            "expiresAt": "2027-01-01T00:00:00Z",
            "apiEndpoints": ["https://api.example.com"],
            "registrationUrl": "https://www.example.com/#/register",
            "downloadPageUrl": "https://download.example.com/download/index.html",
            "bootstrapMirrors": ["https://cdn.example.com/manifest.json"],
            "migrationNotice": None,
        }

    def _validate(self, payload: dict) -> None:
        validator.validate_payload(payload, now=self.now)

    def _updates(self) -> dict:
        def channel(version: str, build: int) -> dict:
            return {
                "version": version,
                "build": build,
                "downloadUrl": "https://download.example.com/download/index.html",
                "required": False,
                "title": "New version",
                "message": "A new client version is available.",
            }

        return {
            "android": channel("2.3.2", 742),
            "desktop": channel("7.24.5", 72405),
        }

    def test_current_repository_payload_is_valid(self) -> None:
        payload = validator.load_payload(REPOSITORY_ROOT / "manifest.payload.json")
        issued = datetime.fromisoformat(payload["issuedAt"].replace("Z", "+00:00"))
        validator.validate_payload(payload, now=issued + timedelta(seconds=1))

    def test_rejects_duplicate_key_in_nested_object(self) -> None:
        source = json.dumps(self.payload)
        source = source.replace(
            '"migrationNotice": null',
            '"migrationNotice": {"id": "one", "id": "two"}',
        )
        with self.assertRaisesRegex(validator.PayloadValidationError, "duplicate JSON key: id"):
            validator.parse_payload_json(source)

    def test_rejects_ip_literals_and_non_public_hostnames(self) -> None:
        for endpoint in (
            "https://127.0.0.1",
            "https://192.168.1.20",
            "https://localhost",
            "https://service.local",
        ):
            with self.subTest(endpoint=endpoint):
                payload = copy.deepcopy(self.payload)
                payload["apiEndpoints"] = [endpoint]
                with self.assertRaisesRegex(
                    validator.PayloadValidationError, "public DNS host"
                ):
                    self._validate(payload)

    def test_rejects_zero_url_port(self) -> None:
        self.payload["apiEndpoints"] = ["https://api.example.com:0"]
        with self.assertRaisesRegex(
            validator.PayloadValidationError,
            "port must be from 1 to 65535",
        ):
            self._validate(self.payload)

    def test_rejects_expired_payload(self) -> None:
        with self.assertRaisesRegex(validator.PayloadValidationError, "must be in the future"):
            validator.validate_payload(
                self.payload,
                now=datetime(2028, 1, 1, tzinfo=timezone.utc),
            )

    def test_accepts_complete_updates(self) -> None:
        self.payload["updates"] = self._updates()
        self._validate(self.payload)

    def test_rejects_blank_migration_notice_text(self) -> None:
        notice = {
            "id": "domain-change",
            "title": "New domain",
            "message": "The service endpoint changed.",
            "autoApply": True,
            "required": False,
        }
        for field in ("id", "title", "message"):
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload)
                payload["migrationNotice"] = dict(notice, **{field: "   "})
                with self.assertRaisesRegex(
                    validator.PayloadValidationError,
                    "must not be blank",
                ):
                    self._validate(payload)

    def test_rejects_missing_or_unexpected_update_fields(self) -> None:
        for mutation, expected in (
            (lambda update: update.pop("message"), "missing field: message"),
            (lambda update: update.update({"channel": "stable"}), "unexpected field: channel"),
            (lambda update: update.update({"version": "2.3"}), "must be major.minor.patch"),
        ):
            with self.subTest(expected=expected):
                payload = copy.deepcopy(self.payload)
                payload["updates"] = self._updates()
                mutation(payload["updates"]["android"])
                with self.assertRaisesRegex(validator.PayloadValidationError, expected):
                    self._validate(payload)


if __name__ == "__main__":
    unittest.main()
