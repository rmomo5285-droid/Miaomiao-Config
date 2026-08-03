#!/usr/bin/env bash

set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

readonly SOURCE_MANIFEST=${1:-/var/www/cdn/manifest.json}
readonly DEPLOY_COMMAND=/usr/local/sbin/miaomiao-manifest-deploy
readonly TARGET_MANIFEST=/var/www/cdn/manifest.json
readonly CONFIG_JSON=/var/www/cdn/config.json

fail() {
  printf 'Manifest deployment test failed: %s\n' "$*" >&2
  exit 1
}

file_sha256() {
  sha256sum "$1" | awk '{print $1}'
}

[[ $(id -u) -eq 0 ]] || fail 'the behavior test must run as root'
[[ -x "$DEPLOY_COMMAND" && ! -L "$DEPLOY_COMMAND" ]] || fail 'the deploy command is missing or unsafe'
[[ -f "$SOURCE_MANIFEST" && ! -L "$SOURCE_MANIFEST" ]] || fail 'the source manifest is missing or unsafe'
[[ -f "$TARGET_MANIFEST" && ! -L "$TARGET_MANIFEST" ]] || fail 'the target manifest is missing or unsafe'
[[ -f "$CONFIG_JSON" && ! -L "$CONFIG_JSON" ]] || fail 'config.json is missing or unsafe'

test_dir=$(mktemp -d /tmp/miaomiao-manifest-behavior.XXXXXX)
cleanup() {
  rm -rf -- "$test_dir"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

cp -- "$SOURCE_MANIFEST" "$test_dir/valid.json"
python3 - "$test_dir" <<'PY'
import base64
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
raw = (root / "valid.json").read_bytes()
envelope = json.loads(raw)

(root / "empty.json").write_bytes(b"")
(root / "oversized.json").write_bytes(b"x" * 262_145)

duplicate = b'{"algorithm":"ECDSA_P256_SHA256",' + raw.lstrip()[1:]
(root / "duplicate-key.json").write_bytes(duplicate)

bad_base64 = dict(envelope, payload="***")
(root / "bad-base64.json").write_text(
    json.dumps(bad_base64, separators=(",", ":")), encoding="utf-8"
)

signature = bytearray(base64.b64decode(envelope["signature"], validate=True))
signature[-1] ^= 1
bad_signature = dict(
    envelope,
    signature=base64.b64encode(signature).decode("ascii"),
)
(root / "bad-signature.json").write_text(
    json.dumps(bad_signature, separators=(",", ":")), encoding="utf-8"
)
PY

config_sha256=$(file_sha256 "$CONFIG_JSON")
target_sha256=$(file_sha256 "$TARGET_MANIFEST")

assert_unchanged() {
  [[ $(file_sha256 "$CONFIG_JSON") == "$config_sha256" ]] \
    || fail 'config.json changed during a deployment test'
  [[ $(file_sha256 "$TARGET_MANIFEST") == "$target_sha256" ]] \
    || fail 'the target manifest changed after a rejected input'
}

expect_rejected() {
  local case_name=$1
  local case_file=$2
  local output
  local status

  set +e
  output=$(env -u SSH_ORIGINAL_COMMAND -u SSH_TTY "$DEPLOY_COMMAND" < "$case_file" 2>&1)
  status=$?
  set -e
  (( status != 0 )) || fail "$case_name was unexpectedly accepted"
  [[ $output == *'Manifest deployment rejected:'* ]] \
    || fail "$case_name did not fail through the deployment guard"
  assert_unchanged
  printf 'Rejected as expected: %s\n' "$case_name"
}

expect_rejected empty "$test_dir/empty.json"
expect_rejected oversized "$test_dir/oversized.json"
expect_rejected duplicate-key "$test_dir/duplicate-key.json"
expect_rejected bad-base64 "$test_dir/bad-base64.json"
expect_rejected bad-signature "$test_dir/bad-signature.json"

env -u SSH_ORIGINAL_COMMAND -u SSH_TTY "$DEPLOY_COMMAND" < "$test_dir/valid.json" >/dev/null
[[ $(file_sha256 "$TARGET_MANIFEST") == "$(file_sha256 "$test_dir/valid.json")" ]] \
  || fail 'an idempotent valid deployment did not preserve exact envelope bytes'
[[ $(file_sha256 "$CONFIG_JSON") == "$config_sha256" ]] \
  || fail 'config.json changed during the valid deployment test'

printf 'Manifest deployment behavior tests passed: target_sha256=%s config_json_sha256=%s\n' \
  "$(file_sha256 "$TARGET_MANIFEST")" "$config_sha256"
