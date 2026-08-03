#!/usr/bin/env bash

set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

readonly PUBLIC_KEY_FILE=${1:-/tmp/miaomiao-manifest-bootstrap/miaomiao-deploy-key.pub}
readonly EXPECTED_FINGERPRINT=${2:-}
readonly AUTHORIZED_KEYS=/root/.ssh/authorized_keys
readonly FORCED_COMMAND=/usr/local/sbin/miaomiao-manifest-deploy

fail() {
  printf 'Deploy-key restriction failed: %s\n' "$*" >&2
  exit 1
}

[[ $(id -u) -eq 0 ]] || fail 'this restriction script must run as root'
[[ -n $EXPECTED_FINGERPRINT ]] || fail 'the expected ED25519 fingerprint is required'
[[ $EXPECTED_FINGERPRINT =~ ^SHA256:[A-Za-z0-9+/]{43}$ ]] \
  || fail 'the expected fingerprint format is invalid'
[[ -f "$PUBLIC_KEY_FILE" && ! -L "$PUBLIC_KEY_FILE" ]] \
  || fail 'the deploy public key is missing or unsafe'
[[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] \
  || fail 'authorized_keys is missing or unsafe'
[[ $(stat -c '%U:%G:%a' /root/.ssh) == root:root:700 ]] \
  || fail '/root/.ssh permissions are unsafe'
[[ $(stat -c '%U:%G:%a' "$AUTHORIZED_KEYS") == root:root:600 ]] \
  || fail 'authorized_keys permissions are unsafe'
[[ -x "$FORCED_COMMAND" && ! -L "$FORCED_COMMAND" ]] \
  || fail 'the forced deploy command is missing or unsafe'

mapfile -t public_key_lines < <(sed '/^[[:space:]]*$/d' "$PUBLIC_KEY_FILE")
(( ${#public_key_lines[@]} == 1 )) || fail 'the deploy public key must contain exactly one line'
public_key_line=${public_key_lines[0]%$'\r'}
read -r key_type key_data key_comment key_extra <<< "$public_key_line"
[[ $key_type == ssh-ed25519 && -n $key_data && -z ${key_extra:-} ]] \
  || fail 'the deploy public key line is invalid'

actual_fingerprint=$(ssh-keygen -lf "$PUBLIC_KEY_FILE" -E sha256 | awk 'NR == 1 {print $2}')
[[ $actual_fingerprint == "$EXPECTED_FINGERPRINT" ]] \
  || fail 'the deploy public key fingerprint does not match'

restricted_line="restrict,command=\"$FORCED_COMMAND\" $key_type $key_data $key_comment"
bare_count=$(grep -Fxc -- "$public_key_line" "$AUTHORIZED_KEYS" || true)
restricted_count=$(grep -Fxc -- "$restricted_line" "$AUTHORIZED_KEYS" || true)

if (( restricted_count == 1 && bare_count == 0 )); then
  printf 'Deploy key is already restricted: %s\n' "$EXPECTED_FINGERPRINT"
  exit 0
fi
(( bare_count == 1 && restricted_count == 0 )) \
  || fail 'expected exactly one bare deploy key and no restricted duplicate'

authorized_keys_new=$(mktemp /root/.ssh/.authorized_keys.new.XXXXXX)
cleanup() {
  rm -f -- "$authorized_keys_new"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

replaced=0
while IFS= read -r line || [[ -n $line ]]; do
  if [[ $line == "$public_key_line" ]]; then
    printf '%s\n' "$restricted_line" >> "$authorized_keys_new"
    replaced=$((replaced + 1))
  else
    printf '%s\n' "$line" >> "$authorized_keys_new"
  fi
done < "$AUTHORIZED_KEYS"
(( replaced == 1 )) || fail 'the deploy key replacement count is invalid'

chown root:root "$authorized_keys_new"
chmod 0600 "$authorized_keys_new"
ssh-keygen -lf "$authorized_keys_new" -E sha256 | grep -F "$EXPECTED_FINGERPRINT" >/dev/null \
  || fail 'the staged authorized_keys file does not contain the deploy key'

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="${AUTHORIZED_KEYS}.bak-miaomiao-${timestamp}"
cp -a -- "$AUTHORIZED_KEYS" "$backup"
mv -Tf -- "$authorized_keys_new" "$AUTHORIZED_KEYS"
sshd -t || {
  cp -a -- "$backup" "$AUTHORIZED_KEYS"
  fail 'sshd validation failed; authorized_keys was restored'
}

printf 'Deploy key restricted: fingerprint=%s backup=%s\n' \
  "$EXPECTED_FINGERPRINT" "$backup"
