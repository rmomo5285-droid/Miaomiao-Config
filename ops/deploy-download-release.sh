#!/usr/bin/env bash
set -Eeuo pipefail

readonly ANDROID_TAG=v2.3.4
readonly DESKTOP_TAG=v7.24.6
readonly TARGET_DIR=/var/www/download
readonly BACKUP_ROOT=/var/backups/miaomiao-download
readonly NGINX_LINK=/etc/nginx/sites-enabled/download.vpnmiao.com
readonly NGINX_CONFIG=$(readlink -f "$NGINX_LINK")
readonly SOURCE_INDEX=${1:-/tmp/miaomiao-download-index.html}
readonly SOURCE_COUNTER=${2:-/tmp/miaomiao-download-counter.py}
readonly SOURCE_SERVICE=${3:-/tmp/miaomiao-download-counter.service}
readonly SOURCE_NGINX=${4:-/tmp/nginx-miaomiao-download.conf}
readonly STAMP=$(date -u +%Y%m%dT%H%M%SZ)
readonly STAGING_DIR=${MIAOMIAO_REUSE_STAGING:-/var/www/.miaomiao-download-staging-${STAMP}}
readonly BACKUP_DIR=${BACKUP_ROOT}/${STAMP}-before-${ANDROID_TAG}-${DESKTOP_TAG}
readonly FAILED_DIR=${BACKUP_ROOT}/${STAMP}-failed-new-release

SWAPPED=0
NGINX_BACKUP=
SERVICE_STARTED=0

fail() {
  printf 'Download release deployment failed: %s\n' "$*" >&2
  exit 1
}

rollback() {
  local status=$?
  if (( SWAPPED == 1 )); then
    mkdir -p "$FAILED_DIR"
    find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -exec mv -t "$FAILED_DIR" -- {} + 2>/dev/null || true
    find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -exec mv -t "$TARGET_DIR" -- {} + 2>/dev/null || true
  fi
  if [[ -n "$NGINX_BACKUP" && -f "$NGINX_BACKUP" ]]; then
    cp -a "$NGINX_BACKUP" "$NGINX_CONFIG"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  fi
  if (( SERVICE_STARTED == 1 )); then
    systemctl disable --now miaomiao-download-counter.service >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap rollback ERR

[[ $(id -u) -eq 0 ]] || fail 'run as root'
[[ -f "$SOURCE_INDEX" ]] || fail "missing index source: $SOURCE_INDEX"
[[ -f "$SOURCE_COUNTER" ]] || fail "missing counter source: $SOURCE_COUNTER"
[[ -f "$SOURCE_SERVICE" ]] || fail "missing service source: $SOURCE_SERVICE"
[[ -f "$SOURCE_NGINX" ]] || fail "missing nginx source: $SOURCE_NGINX"
[[ -d "$TARGET_DIR" ]] || fail "missing target directory: $TARGET_DIR"
[[ -f "$NGINX_CONFIG" ]] || fail "missing nginx config: $NGINX_CONFIG"
for command in curl sha256sum nginx systemctl readlink; do
  command -v "$command" >/dev/null || fail "missing command: $command"
done

available_kib=$(df -Pk "$TARGET_DIR" | awk 'NR == 2 { print $4 }')
if [[ -n ${MIAOMIAO_REUSE_STAGING:-} ]]; then
  [[ $STAGING_DIR == "$BACKUP_ROOT"/* ]] || fail 'reused staging must be inside the download backup root'
  [[ -d "$STAGING_DIR" ]] || fail "reused staging directory does not exist: $STAGING_DIR"
  (( available_kib >= 100000 )) || fail 'less than 100 MiB is available for the atomic switch'
else
  (( available_kib >= 1800000 )) || fail 'less than 1.8 GiB is available for staged downloads and backup'
fi

install -d -m 0755 "$STAGING_DIR" "$BACKUP_DIR"
install -m 0644 "$SOURCE_INDEX" "$STAGING_DIR/index.html"

download() {
  local repository=$1 tag=$2 name=$3 target=${4:-$3}
  curl --fail --location --silent --show-error --retry 5 --retry-all-errors \
    --output "$STAGING_DIR/$target" \
    "https://github.com/${repository}/releases/download/${tag}/${name}"
}

android_files=(
  miaomiao_2.3.4_arm64-v8a.apk
  miaomiao_2.3.4_armeabi-v7a.apk
  miaomiao_2.3.4_universal.apk
  miaomiao_2.3.4_x86.apk
  miaomiao_2.3.4_x86_64.apk
)
desktop_files=(
  Miaomiao-7.24.6-windows-arm64.zip
  Miaomiao-7.24.6-windows-x64.zip
  Miaomiao-7.24.6-macos-arm64.dmg
  Miaomiao-7.24.6-macos-x64.dmg
  miaomiao_7.24.6_amd64.deb
  miaomiao_7.24.6_arm64.deb
  miaomiao-7.24.6-1.x86_64.rpm
  miaomiao-7.24.6-1.aarch64.rpm
)

if [[ -z ${MIAOMIAO_REUSE_STAGING:-} ]]; then
  for file in "${android_files[@]}"; do
    download rmomo5285-droid/Miaomiao-Android "$ANDROID_TAG" "$file"
    download rmomo5285-droid/Miaomiao-Android "$ANDROID_TAG" "$file.asc"
  done
  download rmomo5285-droid/Miaomiao-Android "$ANDROID_TAG" SHA256SUMS SHA256SUMS-android-v2.3.4.txt
  download rmomo5285-droid/Miaomiao-Android "$ANDROID_TAG" SHA256SUMS.asc SHA256SUMS-android-v2.3.4.txt.asc

  for file in "${desktop_files[@]}"; do
    download rmomo5285-droid/Miaomiao-Desktop "$DESKTOP_TAG" "$file"
    download rmomo5285-droid/Miaomiao-Desktop "$DESKTOP_TAG" "$file.asc"
  done
  download rmomo5285-droid/Miaomiao-Desktop "$DESKTOP_TAG" SHA256SUMS SHA256SUMS-desktop-v7.24.6.txt
  download rmomo5285-droid/Miaomiao-Desktop "$DESKTOP_TAG" SHA256SUMS.asc SHA256SUMS-desktop-v7.24.6.txt.asc
  download rmomo5285-droid/Miaomiao-Desktop "$DESKTOP_TAG" miaomiao-release-public-key.asc
fi

for file in "${android_files[@]}" "${desktop_files[@]}"; do
  [[ -f "$STAGING_DIR/$file" ]] || fail "missing staged release: $file"
  [[ -f "$STAGING_DIR/$file.asc" ]] || fail "missing staged signature: $file.asc"
done
for file in SHA256SUMS-android-v2.3.4.txt SHA256SUMS-android-v2.3.4.txt.asc \
  SHA256SUMS-desktop-v7.24.6.txt SHA256SUMS-desktop-v7.24.6.txt.asc \
  miaomiao-release-public-key.asc; do
  [[ -f "$STAGING_DIR/$file" ]] || fail "missing staged verification file: $file"
done

cat > "$STAGING_DIR/EXPECTED_SHA256SUMS" <<'SUMS'
ec2f3aa6cf7dd1bd85e57f7f9ffa5eee1d225f67701f32645d648329971ee8ec  miaomiao_2.3.4_arm64-v8a.apk
aba097c24f5cb7e63a3e41a58b5f5afa0813cbad10b6b3be807012757b168cba  miaomiao_2.3.4_armeabi-v7a.apk
aedde7f4f9234fc484900e1c1ce8938fd0011aa4be84a4b6bb223cf1781265c5  miaomiao_2.3.4_universal.apk
021e588ac66a945c641a9bddab80f62bacdb2458b50684fba4a2cd5e28cce595  miaomiao_2.3.4_x86.apk
65fb9e213a6c6a94564e67bcf398dc377b03a44ac952817d419c9dffd9e99989  miaomiao_2.3.4_x86_64.apk
a7c84cf5f47846cf0a1da08a0b7e67bccb9866c4c836e07ea2a72df211bfe5eb  Miaomiao-7.24.6-windows-arm64.zip
c3fbf7ceb4bce7ea91697fd034f8254fd870c008109ee114d0a0f8fafb10cfb8  Miaomiao-7.24.6-windows-x64.zip
4a23b3986b398ac5a8b48cf53d6a41d460bcf4febdaaffae6a92751c515817fb  Miaomiao-7.24.6-macos-arm64.dmg
05a61f8873c2a129033d4499701e407f76a66f5d8f4fb8f5293c1d7cec4de7e7  Miaomiao-7.24.6-macos-x64.dmg
808a788759eae56a346da8f94d46274dc561e8264988cfb7d9234cfe2abb6e2f  miaomiao_7.24.6_amd64.deb
427b7a6e7b116d6ad5d0afdd28b760cdad923ce016fe958d038cadd2e12391f3  miaomiao_7.24.6_arm64.deb
8df537320d2d3dcaeddffa3bd1e9d3fd04b720df608cd2a94d5bd741567c2ade  miaomiao-7.24.6-1.x86_64.rpm
595f4bc147dc520ca0e5bd1617b6f23399e329bd9d776bbfd240fc17321e41ed  miaomiao-7.24.6-1.aarch64.rpm
SUMS
(cd "$STAGING_DIR" && sha256sum --check EXPECTED_SHA256SUMS)
chmod 0644 "$STAGING_DIR"/*

install -d -m 0700 "$BACKUP_ROOT/nginx"
NGINX_BACKUP=${BACKUP_ROOT}/nginx/${STAMP}-download.vpnmiao.com.conf
cp -a "$NGINX_CONFIG" "$NGINX_BACKUP"
install -d -m 0755 /usr/local/lib/miaomiao
install -m 0755 "$SOURCE_COUNTER" /usr/local/lib/miaomiao/miaomiao-download-counter.py
install -d -o www-data -g www-data -m 0750 /var/lib/miaomiao-download-counter
install -m 0644 "$SOURCE_SERVICE" /etc/systemd/system/miaomiao-download-counter.service
install -m 0644 "$SOURCE_NGINX" "$NGINX_CONFIG"
nginx -t

find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -exec mv -t "$BACKUP_DIR" -- {} +
find "$STAGING_DIR" -mindepth 1 -maxdepth 1 -exec mv -t "$TARGET_DIR" -- {} +
rmdir "$STAGING_DIR"
SWAPPED=1
systemctl daemon-reload
SERVICE_STARTED=1
systemctl enable --now miaomiao-download-counter.service
systemctl is-active --quiet miaomiao-download-counter.service
counter_ready=0
for _ in {1..40}; do
  if curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:18765/stats >/dev/null 2>&1; then
    counter_ready=1
    break
  fi
  sleep 0.25
done
(( counter_ready == 1 )) || fail 'download counter did not become ready within 10 seconds'
systemctl reload nginx

printf 'Smoke test: counter service active.\n'
curl --noproxy '*' --fail --silent --show-error --resolve download.vpnmiao.com:443:127.0.0.1 \
  https://download.vpnmiao.com/download/index.html | grep -Fq 'Android 2.3.4'
printf 'Smoke test: release page current.\n'
curl --noproxy '*' --fail --silent --show-error --head --resolve download.vpnmiao.com:443:127.0.0.1 \
  https://download.vpnmiao.com/download/Miaomiao-7.24.6-macos-arm64.dmg >/dev/null
printf 'Smoke test: DMG internal download route works.\n'
curl --noproxy '*' --fail --silent --show-error --resolve download.vpnmiao.com:443:127.0.0.1 \
  https://download.vpnmiao.com/download/stats.json | grep -Fq '"total"'
printf 'Smoke test: public download statistics work.\n'

SWAPPED=0
SERVICE_STARTED=0
trap - ERR
printf 'Download center deployed. backup=%s nginx_backup=%s\n' "$BACKUP_DIR" "$NGINX_BACKUP"
