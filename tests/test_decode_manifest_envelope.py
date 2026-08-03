from __future__ import annotations

import base64
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "decode-manifest-envelope.py"
SPEC = importlib.util.spec_from_file_location("decode_manifest_envelope", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
decoder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = decoder
SPEC.loader.exec_module(decoder)


def envelope_bytes(payload: bytes = b'{"schema":1}', signature: bytes = b"s" * 64) -> bytes:
    return json.dumps(
        {
            "algorithm": decoder.ALGORITHM,
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        },
        separators=(",", ":"),
    ).encode("utf-8")


class DecodeManifestEnvelopeTests(unittest.TestCase):
    def test_decodes_exact_bytes_to_caller_paths(self) -> None:
        payload = b'{"schema":1,"nested":{"enabled":true}}\n'
        signature = bytes(range(64))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            envelope_path = root / "manifest.json"
            payload_path = root / "payload.json"
            signature_path = root / "signature.bin"
            envelope_path.write_bytes(envelope_bytes(payload, signature))

            sizes = decoder.decode_manifest_envelope(
                envelope_path, payload_path, signature_path
            )

            self.assertEqual(sizes, (len(payload), len(signature)))
            self.assertEqual(payload_path.read_bytes(), payload)
            self.assertEqual(signature_path.read_bytes(), signature)

    def test_rejects_duplicate_keys_recursively_in_envelope(self) -> None:
        raw = (
            b'{"algorithm":"ECDSA_P256_SHA256","payload":"e30=",'
            b'"signature":"c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzcw==",'
            b'"extra":{"id":1,"id":2}}'
        )
        with self.assertRaisesRegex(decoder.EnvelopeDecodeError, "duplicate JSON key: id"):
            decoder.decode_envelope_bytes(raw)

    def test_rejects_duplicate_keys_recursively_in_payload(self) -> None:
        payload = b'{"nested":{"id":1,"id":2}}'
        with self.assertRaisesRegex(decoder.EnvelopeDecodeError, "duplicate JSON key: id"):
            decoder.decode_envelope_bytes(envelope_bytes(payload))

    def test_requires_exact_fields_and_algorithm(self) -> None:
        valid = json.loads(envelope_bytes())
        cases = []
        missing = dict(valid)
        missing.pop("signature")
        cases.append((missing, "missing field: signature"))
        extra = dict(valid, version=1)
        cases.append((extra, "unexpected field: version"))
        algorithm = dict(valid, algorithm="none")
        cases.append((algorithm, "algorithm must be ECDSA_P256_SHA256"))

        for envelope, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(decoder.EnvelopeDecodeError, expected):
                    decoder.decode_envelope_bytes(json.dumps(envelope).encode("utf-8"))

    def test_rejects_noncanonical_base64(self) -> None:
        valid = json.loads(envelope_bytes())
        for encoded in ("e30", "e30=\n", "AB=="):
            with self.subTest(encoded=repr(encoded)):
                envelope = dict(valid, payload=encoded)
                with self.assertRaisesRegex(
                    decoder.EnvelopeDecodeError, "canonical RFC 4648 base64"
                ):
                    decoder.decode_envelope_bytes(json.dumps(envelope).encode("utf-8"))

    def test_rejects_invalid_utf8_and_non_object_payloads(self) -> None:
        for payload, expected in (
            (b"\xff", "decoded payload must be UTF-8"),
            (b"[]", "decoded payload must be a JSON object"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(decoder.EnvelopeDecodeError, expected):
                    decoder.decode_envelope_bytes(envelope_bytes(payload))

    def test_enforces_deployment_size_limits(self) -> None:
        cases = (
            (b"x" * (decoder.MAX_ENVELOPE_BYTES + 1), "envelope exceeds"),
            (
                envelope_bytes(b'{' + b'"padding":"' + b"x" * decoder.MAX_PAYLOAD_BYTES + b'"}'),
                "decoded payload exceeds",
            ),
            (envelope_bytes(signature=b"s" * 63), "signature must be 64 to 80 bytes"),
            (envelope_bytes(signature=b"s" * 81), "signature must be 64 to 80 bytes"),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(decoder.EnvelopeDecodeError, expected):
                    decoder.decode_envelope_bytes(raw)


if __name__ == "__main__":
    unittest.main()
