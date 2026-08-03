#!/usr/bin/env bash

set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 027

readonly SOURCE_DIR=${1:-/tmp/miaomiao-manifest-bootstrap}
readonly TARGET_DIR=/var/www/cdn
readonly TARGET_MANIFEST="$TARGET_DIR/manifest.json"
readonly CONFIG_JSON="$TARGET_DIR/config.json"
readonly PUBLIC_KEY_DIR=/etc/miaomiao
readonly PUBLIC_KEY="$PUBLIC_KEY_DIR/manifest-signing-public.pem"
readonly TOOL_DIR=/usr/local/libexec/miaomiao
readonly DECODER="$TOOL_DIR/decode-manifest-envelope.py"
readonly VALIDATOR="$TOOL_DIR/validate-payload.py"
readonly DEPLOY_COMMAND=/usr/local/sbin/miaomiao-manifest-deploy
readonly NGINX_CONFIG=/etc/nginx/sites-available/cdn.vpnmiao.com
readonly NGINX_SNIPPET_DIR=/etc/nginx/snippets
readonly NGINX_SNIPPET="$NGINX_SNIPPET_DIR/miaomiao-manifest.conf"
readonly NGINX_INCLUDE='    include /etc/nginx/snippets/miaomiao-manifest.conf;'

fail() {
  printf 'Manifest installation failed: %s\n' "$*" >&2
  exit 1
}

assert_secure_directory() {
  local directory=$1
  local label=$2
  local mode

  [[ -d "$directory" && ! -L "$directory" ]] || fail "$label is missing or is a symlink"
  [[ $(stat -c '%U:%G' "$directory") == root:root ]] || fail "$label must be owned by root:root"
  mode=$(stat -c '%a' "$directory")
  [[ $mode =~ ^[0-7]{3,4}$ ]] || fail "$label permissions are invalid"
  (( (8#$mode & 0022) == 0 )) || fail "$label must not be writable by group or other"
}

require_source_file() {
  local file=$1

  [[ -f "$SOURCE_DIR/$file" && ! -L "$SOURCE_DIR/$file" ]] \
    || fail "source file $file is missing or unsafe"
  [[ $(stat -c '%U:%G' "$SOURCE_DIR/$file") == root:root ]] \
    || fail "source file $file must be owned by root:root"
}

[[ $(id -u) -eq 0 ]] || fail 'this installer must run as root'

for command in bash python3 jq openssl flock dd stat mktemp sha256sum mv install nginx systemctl; do
  command -v "$command" >/dev/null || fail "required command is missing: $command"
done

assert_secure_directory "$SOURCE_DIR" 'the source directory'
assert_secure_directory "$TARGET_DIR" 'the target directory'
[[ -f "$CONFIG_JSON" && ! -L "$CONFIG_JSON" ]] || fail 'config.json is missing or unsafe'
[[ -f "$NGINX_CONFIG" && ! -L "$NGINX_CONFIG" ]] || fail 'the Nginx site config is missing or unsafe'

for source_file in \
  miaomiao-manifest-deploy \
  nginx-miaomiao-manifest.conf \
  manifest-signing-public.pem \
  decode-manifest-envelope.py \
  validate-payload.py \
  manifest.json; do
  require_source_file "$source_file"
done

bash -n "$SOURCE_DIR/miaomiao-manifest-deploy"

validation_dir=$(mktemp -d /tmp/miaomiao-manifest-validation.XXXXXX)
config_new=''
cleanup() {
  rm -rf -- "$validation_dir"
  [[ -z $config_new ]] || rm -f -- "$config_new"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

python3 "$SOURCE_DIR/decode-manifest-envelope.py" \
  "$SOURCE_DIR/manifest.json" \
  "$validation_dir/payload.json" \
  "$validation_dir/signature.bin" >/dev/null
python3 "$SOURCE_DIR/validate-payload.py" "$validation_dir/payload.json" >/dev/null
openssl dgst -sha256 \
  -verify "$SOURCE_DIR/manifest-signing-public.pem" \
  -signature "$validation_dir/signature.bin" \
  "$validation_dir/payload.json" >/dev/null

config_json_sha256=$(sha256sum "$CONFIG_JSON" | awk '{print $1}')

install -d -o root -g root -m 0755 "$PUBLIC_KEY_DIR" "$TOOL_DIR" "$NGINX_SNIPPET_DIR"
install -o root -g root -m 0644 "$SOURCE_DIR/manifest-signing-public.pem" "$PUBLIC_KEY"
install -o root -g root -m 0644 "$SOURCE_DIR/decode-manifest-envelope.py" "$DECODER"
install -o root -g root -m 0644 "$SOURCE_DIR/validate-payload.py" "$VALIDATOR"
install -o root -g root -m 0755 "$SOURCE_DIR/miaomiao-manifest-deploy" "$DEPLOY_COMMAND"
install -o root -g root -m 0644 "$SOURCE_DIR/nginx-miaomiao-manifest.conf" "$NGINX_SNIPPET"

env -u SSH_ORIGINAL_COMMAND -u SSH_TTY "$DEPLOY_COMMAND" < "$SOURCE_DIR/manifest.json"
[[ -f "$TARGET_MANIFEST" && ! -L "$TARGET_MANIFEST" ]] \
  || fail 'the signed manifest was not deployed'

mapfile -t include_lines < <(grep -nF "$NGINX_INCLUDE" "$NGINX_CONFIG" || true)
(( ${#include_lines[@]} <= 1 )) || fail 'the Nginx snippet include appears more than once'

backup=''
rollback_nginx_config() {
  if [[ -n $backup ]]; then
    cp -a -- "$backup" "$NGINX_CONFIG"
    if nginx -t; then
      systemctl reload nginx || true
    fi
  fi
}

if (( ${#include_lines[@]} == 0 )); then
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  backup="${NGINX_CONFIG}.bak-manifest-${timestamp}"
  cp -a -- "$NGINX_CONFIG" "$backup"
  config_new=$(mktemp "${NGINX_CONFIG}.new.XXXXXX")

  python3 - "$NGINX_CONFIG" "$config_new" "$NGINX_INCLUDE" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
include = sys.argv[3]
raw = source.read_bytes()
marker = b"    autoindex off;\n"
if raw.count(marker) != 1:
    raise SystemExit("expected exactly one HTTPS autoindex marker")
destination.write_bytes(raw.replace(marker, marker + include.encode("ascii") + b"\n", 1))
PY

  chown --reference="$NGINX_CONFIG" "$config_new"
  chmod --reference="$NGINX_CONFIG" "$config_new"
  mv -Tf -- "$config_new" "$NGINX_CONFIG"
fi

if ! nginx -t; then
  rollback_nginx_config
  fail 'Nginx rejected the manifest location snippet'
fi

if ! systemctl reload nginx; then
  rollback_nginx_config
  fail 'Nginx reload failed; the previous site config was restored'
fi
if [[ $(systemctl is-active nginx) != active ]]; then
  rollback_nginx_config
  fail 'Nginx is not active after reload; the previous site config was restored'
fi
[[ $(sha256sum "$CONFIG_JSON" | awk '{print $1}') == "$config_json_sha256" ]] \
  || fail 'config.json changed unexpectedly'

printf 'Manifest installation complete: version=%s config_json_sha256=%s\n' \
  "$(jq -r .version "$validation_dir/payload.json")" "$config_json_sha256"
