#!/usr/bin/env python3
"""Strictly decode a Miaomiao signed-manifest envelope."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


ALGORITHM = "ECDSA_P256_SHA256"
MAX_ENVELOPE_BYTES = 262_144
MAX_PAYLOAD_BYTES = 65_536
MIN_SIGNATURE_BYTES = 64
MAX_SIGNATURE_BYTES = 80
_ENVELOPE_FIELDS = {"algorithm", "payload", "signature"}


class EnvelopeDecodeError(ValueError):
    """Raised when a signed-manifest envelope is not canonical and well formed."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EnvelopeDecodeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_json_number(value: str) -> None:
    raise EnvelopeDecodeError(f"invalid JSON number: {value}")


def _parse_json(raw: bytes, label: str) -> Any:
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise EnvelopeDecodeError(f"{label} must be UTF-8") from None
    try:
        return json.loads(
            source,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_json_number,
        )
    except json.JSONDecodeError as error:
        raise EnvelopeDecodeError(
            f"{label} is invalid JSON at line {error.lineno}, column {error.colno}"
        ) from None


def _decode_canonical_base64(value: Any, label: str) -> bytes:
    if type(value) is not str or not value:
        raise EnvelopeDecodeError(f"{label} must be a non-empty base64 string")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise EnvelopeDecodeError(f"{label} must be canonical RFC 4648 base64") from None
    if base64.b64encode(decoded).decode("ascii") != value:
        raise EnvelopeDecodeError(f"{label} must be canonical RFC 4648 base64")
    return decoded


def decode_envelope_bytes(raw: bytes) -> tuple[bytes, bytes]:
    """Validate and decode envelope bytes without verifying the ECDSA signature."""
    if not raw:
        raise EnvelopeDecodeError("envelope must not be empty")
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise EnvelopeDecodeError(f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes")

    envelope = _parse_json(raw, "envelope")
    if type(envelope) is not dict:
        raise EnvelopeDecodeError("envelope must be a JSON object")
    actual_fields = set(envelope)
    missing = sorted(_ENVELOPE_FIELDS - actual_fields)
    if missing:
        raise EnvelopeDecodeError(f"envelope missing field: {missing[0]}")
    unexpected = sorted(actual_fields - _ENVELOPE_FIELDS)
    if unexpected:
        raise EnvelopeDecodeError(f"envelope has unexpected field: {unexpected[0]}")
    if envelope["algorithm"] != ALGORITHM or type(envelope["algorithm"]) is not str:
        raise EnvelopeDecodeError(f"algorithm must be {ALGORITHM}")

    payload = _decode_canonical_base64(envelope["payload"], "payload")
    signature = _decode_canonical_base64(envelope["signature"], "signature")
    if not payload:
        raise EnvelopeDecodeError("decoded payload must not be empty")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise EnvelopeDecodeError(f"decoded payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    if not MIN_SIGNATURE_BYTES <= len(signature) <= MAX_SIGNATURE_BYTES:
        raise EnvelopeDecodeError(
            f"decoded signature must be {MIN_SIGNATURE_BYTES} to {MAX_SIGNATURE_BYTES} bytes"
        )

    parsed_payload = _parse_json(payload, "decoded payload")
    if type(parsed_payload) is not dict:
        raise EnvelopeDecodeError("decoded payload must be a JSON object")
    return payload, signature


def _read_envelope(path: Path) -> bytes:
    with path.open("rb") as source:
        raw = source.read(MAX_ENVELOPE_BYTES + 1)
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise EnvelopeDecodeError(f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes")
    return raw


def _stage_output(destination: Path, content: bytes) -> Path:
    parent = destination.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _write_outputs(
    payload_path: Path,
    signature_path: Path,
    payload: bytes,
    signature: bytes,
) -> None:
    if os.path.abspath(payload_path) == os.path.abspath(signature_path):
        raise EnvelopeDecodeError("payload and signature output paths must be different")

    staged_payload: Path | None = None
    staged_signature: Path | None = None
    try:
        staged_payload = _stage_output(payload_path, payload)
        staged_signature = _stage_output(signature_path, signature)
        os.replace(staged_payload, payload_path)
        staged_payload = None
        os.replace(staged_signature, signature_path)
        staged_signature = None
    finally:
        if staged_payload is not None:
            staged_payload.unlink(missing_ok=True)
        if staged_signature is not None:
            staged_signature.unlink(missing_ok=True)


def decode_manifest_envelope(
    envelope_path: str | Path,
    payload_path: str | Path,
    signature_path: str | Path,
) -> tuple[int, int]:
    """Decode an envelope into exact payload and signature bytes at caller paths."""
    source = Path(envelope_path)
    payload_destination = Path(payload_path)
    signature_destination = Path(signature_path)
    source_absolute = os.path.abspath(source)
    if source_absolute in {
        os.path.abspath(payload_destination),
        os.path.abspath(signature_destination),
    }:
        raise EnvelopeDecodeError("output paths must not overwrite the envelope")

    payload, signature = decode_envelope_bytes(_read_envelope(source))
    _write_outputs(payload_destination, signature_destination, payload, signature)
    return len(payload), len(signature)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strictly decode a Miaomiao signed-manifest envelope"
    )
    parser.add_argument("envelope", help="signed manifest envelope JSON path")
    parser.add_argument("payload_output", help="decoded payload output path")
    parser.add_argument("signature_output", help="decoded signature output path")
    arguments = parser.parse_args(argv)

    try:
        payload_size, signature_size = decode_manifest_envelope(
            arguments.envelope,
            arguments.payload_output,
            arguments.signature_output,
        )
    except (OSError, EnvelopeDecodeError) as error:
        print(f"Strict envelope validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Decoded payload={payload_size} bytes signature={signature_size} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
