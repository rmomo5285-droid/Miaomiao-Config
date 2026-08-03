#!/usr/bin/env python3
"""Validate a Miaomiao endpoint manifest payload using the Python standard library."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


MAX_PAYLOAD_BYTES = 65_536
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_BUILD = 2_147_483_647
MAX_URL_LENGTH = 2_048

_TOP_LEVEL_REQUIRED = {
    "apiEndpoints",
    "bootstrapMirrors",
    "downloadPageUrl",
    "expiresAt",
    "issuedAt",
    "registrationUrl",
    "schema",
    "version",
}
_TOP_LEVEL_OPTIONAL = {"migrationNotice", "updates"}
_MIGRATION_FIELDS = {"autoApply", "id", "message", "required", "title"}
_UPDATE_FIELDS = {"build", "downloadUrl", "message", "required", "title", "version"}
_VERSION_PATTERN = re.compile(
    r"^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$"
)
_RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class PayloadValidationError(ValueError):
    """Raised when a payload violates the signed-manifest contract."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PayloadValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_json_number(value: str) -> None:
    raise PayloadValidationError(f"invalid JSON number: {value}")


def parse_payload_json(source: str) -> dict[str, Any]:
    """Parse JSON while rejecting duplicate object keys at every nesting level."""
    try:
        payload = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_json_number,
        )
    except json.JSONDecodeError as error:
        raise PayloadValidationError(
            f"invalid JSON at line {error.lineno}, column {error.colno}"
        ) from None
    if type(payload) is not dict:
        raise PayloadValidationError("payload must be a JSON object")
    return payload


def load_payload(path: str | Path) -> dict[str, Any]:
    payload_path = Path(path)
    raw = payload_path.read_bytes()
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise PayloadValidationError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PayloadValidationError("payload must be UTF-8") from None
    return parse_payload_json(source)


def _require_exact_fields(
    value: Any,
    required: set[str],
    *,
    optional: set[str] | None = None,
    context: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise PayloadValidationError(f"{context} must be an object")
    optional = optional or set()
    actual = set(value)
    missing = sorted(required - actual)
    if missing:
        raise PayloadValidationError(f"{context} missing field: {missing[0]}")
    unexpected = sorted(actual - required - optional)
    if unexpected:
        raise PayloadValidationError(f"{context} has unexpected field: {unexpected[0]}")
    return value


def _require_string(value: Any, name: str, maximum: int, *, nonblank: bool = False) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise PayloadValidationError(f"{name} must be a string of 1 to {maximum} characters")
    if nonblank and not value.strip():
        raise PayloadValidationError(f"{name} must not be blank")
    return value


def _validate_public_dns_host(hostname: str, kind: str) -> None:
    host = hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise PayloadValidationError(f"{kind} must use a public DNS host, not an IP literal")

    if "." not in host or host.endswith(".local") or host.endswith(".localhost"):
        raise PayloadValidationError(f"{kind} must use a public DNS host")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise PayloadValidationError(f"{kind} has an invalid DNS host") from None
    if len(ascii_host) > 253 or any(
        not _DNS_LABEL_PATTERN.fullmatch(label) for label in ascii_host.split(".")
    ):
        raise PayloadValidationError(f"{kind} has an invalid DNS host")


def _validate_url(raw: Any, kind: str) -> None:
    url = _require_string(raw, kind, MAX_URL_LENGTH)
    if not url.startswith("https://") or any(character.isspace() for character in url):
        raise PayloadValidationError(f"{kind} must be an absolute HTTPS URL")
    if "\\" in url:
        raise PayloadValidationError(f"{kind} must be an absolute HTTPS URL")
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise PayloadValidationError(f"{kind} is invalid: {error}") from None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise PayloadValidationError(f"{kind} must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise PayloadValidationError(f"{kind} must not contain user information")
    try:
        port = parsed.port
    except ValueError as error:
        raise PayloadValidationError(f"{kind} has an invalid port: {error}") from None
    if port is not None and not 1 <= port <= 65_535:
        raise PayloadValidationError(f"{kind} port must be from 1 to 65535")
    _validate_public_dns_host(parsed.hostname, kind)

    if kind == "API endpoint" and (
        parsed.path not in ("", "/") or parsed.query or parsed.fragment
    ):
        raise PayloadValidationError("API endpoint must be an HTTPS origin")
    if kind == "bootstrap mirror" and parsed.fragment:
        raise PayloadValidationError("bootstrap mirror must not contain a fragment")


def _validate_url_list(value: Any, name: str, kind: str) -> None:
    if type(value) is not list or not 1 <= len(value) <= 8:
        raise PayloadValidationError(f"{name} must contain 1 to 8 URLs")
    for item in value:
        _validate_url(item, kind)
    if len({item.lower() for item in value}) != len(value):
        raise PayloadValidationError(f"{name} must not contain duplicate URLs")


def _parse_timestamp(raw: Any, name: str) -> datetime:
    if type(raw) is not str or not _RFC3339_PATTERN.fullmatch(raw):
        raise PayloadValidationError(f"{name} must be an RFC 3339 timestamp")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise PayloadValidationError(f"{name} must be an RFC 3339 timestamp") from None
    if parsed.tzinfo is None:
        raise PayloadValidationError(f"{name} must include a time-zone offset")
    return parsed.astimezone(timezone.utc)


def _validate_migration_notice(value: Any) -> None:
    if value is None:
        return
    notice = _require_exact_fields(value, _MIGRATION_FIELDS, context="migrationNotice")
    _require_string(notice["id"], "migrationNotice.id", 128, nonblank=True)
    _require_string(notice["title"], "migrationNotice.title", 200, nonblank=True)
    _require_string(notice["message"], "migrationNotice.message", 4_000, nonblank=True)
    if notice["autoApply"] is not True:
        raise PayloadValidationError("migrationNotice.autoApply must be true")
    if type(notice["required"]) is not bool:
        raise PayloadValidationError("migrationNotice.required must be a boolean")


def _validate_update(value: Any, platform: str) -> None:
    update = _require_exact_fields(value, _UPDATE_FIELDS, context=f"updates.{platform}")
    version = _require_string(update["version"], f"updates.{platform}.version", 64)
    if not _VERSION_PATTERN.fullmatch(version):
        raise PayloadValidationError(f"updates.{platform}.version must be major.minor.patch")
    if type(update["build"]) is not int or not 1 <= update["build"] <= MAX_BUILD:
        raise PayloadValidationError(
            f"updates.{platform}.build must be an integer from 1 to {MAX_BUILD}"
        )
    _validate_url(update["downloadUrl"], f"{platform} update download URL")
    if type(update["required"]) is not bool:
        raise PayloadValidationError(f"updates.{platform}.required must be a boolean")
    _require_string(update["title"], f"updates.{platform}.title", 200, nonblank=True)
    _require_string(update["message"], f"updates.{platform}.message", 4_000, nonblank=True)


def validate_payload(payload: Any, *, now: datetime | None = None) -> None:
    manifest = _require_exact_fields(
        payload,
        _TOP_LEVEL_REQUIRED,
        optional=_TOP_LEVEL_OPTIONAL,
        context="payload",
    )
    if manifest["schema"] != 1 or type(manifest["schema"]) is not int:
        raise PayloadValidationError("schema must be 1")
    if (
        type(manifest["version"]) is not int
        or not 1 <= manifest["version"] <= MAX_SAFE_INTEGER
    ):
        raise PayloadValidationError(
            f"version must be an integer from 1 to {MAX_SAFE_INTEGER}"
        )

    issued = _parse_timestamp(manifest["issuedAt"], "issuedAt")
    expires = _parse_timestamp(manifest["expiresAt"], "expiresAt")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a time-zone offset")
    current = current.astimezone(timezone.utc)
    if expires <= issued:
        raise PayloadValidationError("expiresAt must be later than issuedAt")
    if issued > current + timedelta(seconds=300):
        raise PayloadValidationError("issuedAt must not be more than 300 seconds in the future")
    if expires <= current:
        raise PayloadValidationError("expiresAt must be in the future")

    _validate_url_list(manifest["apiEndpoints"], "apiEndpoints", "API endpoint")
    _validate_url(manifest["registrationUrl"], "registration URL")
    _validate_url(manifest["downloadPageUrl"], "download page URL")
    _validate_url_list(manifest["bootstrapMirrors"], "bootstrapMirrors", "bootstrap mirror")

    if "migrationNotice" in manifest:
        _validate_migration_notice(manifest["migrationNotice"])
    if "updates" in manifest:
        updates = _require_exact_fields(
            manifest["updates"], {"android", "desktop"}, context="updates"
        )
        _validate_update(updates["android"], "android")
        _validate_update(updates["desktop"], "desktop")


def validate_payload_file(path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    payload = load_payload(path)
    validate_payload(payload, now=now)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Miaomiao manifest payload")
    parser.add_argument("payload", help="path to manifest.payload.json")
    arguments = parser.parse_args(argv)
    try:
        payload = validate_payload_file(arguments.payload)
    except (OSError, PayloadValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Validated manifest payload version {payload['version']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
