# Miaomiao endpoint manifest

This repository publishes the signed endpoint manifest consumed by the Miaomiao
desktop and Android clients. The clients verify every manifest with an embedded
ECDSA P-256 public key before accepting endpoint or migration-notice changes.

The manifest is deliberately narrow. It can only provide API endpoints,
registration and download URLs, bootstrap mirrors, user-facing notices, and
client update metadata. It cannot execute commands, inject arbitrary HTTP
requests, replace proxy profiles, or change proxy cores.

## Publishing

1. Update `manifest.payload.json` and increment `version`.
2. Review the endpoint allow-list and expiry.
3. Push to `main` or run the `Publish signed manifest` workflow.
4. GitHub Actions signs the exact payload bytes and deploys `manifest.json` to
   the `gh-pages` branch.

The installed clients try `https://cdn.vpnmiao.com/manifest.json` first. That
stable URL must serve the same signed envelope values as `public/manifest.json`
and should remain available even when the customer-facing website moves. The
legacy `https://cdn.vpnmiao.com/json` path remains a compatibility alias for the
same signed response. JSON whitespace may differ, so verify the ECDSA signature
instead of comparing the response body hash with `public/manifest.json.sha256`.
GitHub Pages, jsDelivr, and raw GitHub are fallback mirrors, not the only client
delivery path.

`https://cdn.vpnmiao.com/config.json` is the existing Orange configuration
endpoint. This repository does not route, overwrite, or otherwise manage that
path.

Before the first client release, add a second read-only bootstrap mirror on an
independently registered domain and hosting provider. A mirror under another
`vpnmiao.com` subdomain does not protect clients if the whole parent domain is
blocked, and GitHub-only fallbacks may be unreachable on some customer networks.
Add the same URL to this payload and both clients' built-in mirror lists, then
increment the manifest version and sign it again.

To move the service to a new domain, edit only these fields and increment
`version`:

- `apiEndpoints`: Xboard API origins in preferred order.
- `registrationUrl`: browser registration page.
- `downloadPageUrl`: official client download page.
- `bootstrapMirrors`: signed-manifest mirrors; keep the stable CDN URL first.
- `migrationNotice`: optional one-time popup shown after a verified migration.
- `updates`: optional Android and desktop app-version prompts. Both platforms
  are required when this object is present.

Xray and sing-box are not configured here. Desktop core updates continue to use
v2rayN's official upstream release sources.

`worker.js` and `wrangler.toml` provide the first-party CDN path as a
Cloudflare Worker. In the protected `manifest-production` environment, add
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, then set the repository
variable `ENABLE_CLOUDFLARE_DEPLOY=true`. The token needs Workers Scripts edit,
Workers Routes edit, and zone read permissions for `vpnmiao.com`. The workflow
then deploys the same signed envelope to `cdn.vpnmiao.com/manifest.json` (with
`cdn.vpnmiao.com/json` retained as a compatibility alias) and verifies the
primary endpoint's ECDSA signature after deployment. Until the variable and
secrets are configured, the workflow publishes only the independent GitHub
mirrors.

Required Actions secrets:

- `MIAOMIAO_MANIFEST_PRIVATE_KEY`: encrypted ECDSA private key PEM.
- `MIAOMIAO_MANIFEST_KEY_PASSPHRASE`: private-key passphrase.

Optional Cloudflare deployment secrets and variable:

- `CLOUDFLARE_API_TOKEN`: scoped token for the Worker script and route.
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare account containing `vpnmiao.com`.
- `ENABLE_CLOUDFLARE_DEPLOY=true`: repository variable that enables deployment.

Optional VPS deployment secrets and variables:

- `MIAOMIAO_DEPLOY_SSH_PRIVATE_KEY`: dedicated unencrypted ED25519 deploy key.
- `MIAOMIAO_DEPLOY_SSH_KNOWN_HOSTS`: one pinned ED25519 OpenSSH known-hosts line for the VPS.
- `MIAOMIAO_DEPLOY_SSH_HOST`: VPS host name or IP address.
- `MIAOMIAO_DEPLOY_SSH_PORT`: SSH port, normally `22`.
- `MIAOMIAO_DEPLOY_SSH_USER`: forced-command account, currently `root`.
- `MIAOMIAO_DEPLOY_ORIGIN_IP`: public VPS IP used to verify the origin directly.
- `MIAOMIAO_DEPLOY_SSH_KEY_SHA256`: expected deploy-key fingerprint.
- `MIAOMIAO_DEPLOY_HOST_KEY_SHA256`: expected VPS host-key fingerprint.
- `ENABLE_VPS_DEPLOY=true`: enables signed-manifest streaming to the VPS.

The VPS key must be restricted in `authorized_keys` to the root-owned
`ops/miaomiao-manifest-deploy` forced command with OpenSSH's `restrict` option.
The authorized-key entry has this form:

```text
restrict,command="/usr/local/sbin/miaomiao-manifest-deploy" ssh-ed25519 PUBLIC_KEY COMMENT
```

The command accepts only a small JSON envelope on standard input, verifies the
committed ECDSA public key, rejects expiry and version rollback, and atomically
replaces only `/var/www/cdn/manifest.json`. It never writes `config.json` and
does not permit an interactive shell, port forwarding, or file transfer.
`ops/install-vps-manifest.sh` performs the one-time, fail-closed installation:
it validates the uploaded public bundle, installs the forced command and shared
validators, adds only the two exact Nginx locations from the snippet, verifies
the Nginx configuration before reload, and checks that `config.json` did not
change.
`ops/test-vps-manifest-deploy.sh` provides the production smoke test for valid
replay and malformed inputs while asserting that both CDN JSON files retain
their expected hashes.
`ops/restrict-vps-deploy-key.sh` atomically replaces the initially bare deploy
key with the forced-command form after checking the exact ED25519 fingerprint;
run it only while a separate administrator session remains open for recovery.

The public key is intentionally committed in `manifest-signing-public.pem`.
The signing job targets the `manifest-production` Environment. Configure that
Environment with a required reviewer, protect `main`, and require review for
the payload, public key, and workflow paths listed in `.github/CODEOWNERS`.
The daily expiry audit starts failing 30 days before the current manifest
expires so the signed bootstrap path is renewed before clients reject it.

## Migration notice schema

`migrationNotice` is either `null` or a display-only object. Endpoint changes
are applied automatically after signature and version checks; the notice cannot
carry commands or arbitrary request definitions.

```json
{
  "id": "domain-2026-08",
  "title": "服务入口已更新",
  "message": "客户端已自动切换到新的服务入口，本地节点不受影响。",
  "autoApply": true,
  "required": true
}
```

## Client update schema

Only publish `updates` after every supported client can parse this optional
field. Set each platform to the version that is already available from the
download URL, then increment the top-level manifest `version`. A target equal to
the installed app does not produce a popup. Optional updates can be dismissed;
required updates are shown again until the installed version catches up.

```json
"updates": {
  "android": {
    "version": "2.3.2",
    "build": 742,
    "downloadUrl": "https://download.vpnmiao.com/download/index.html",
    "required": false,
    "title": "发现新版本",
    "message": "喵喵 Android 客户端有新版本可用。"
  },
  "desktop": {
    "version": "7.24.5",
    "build": 72405,
    "downloadUrl": "https://download.vpnmiao.com/download/index.html",
    "required": false,
    "title": "发现新版本",
    "message": "喵喵桌面客户端有新版本可用。"
  }
}
```

The platform `build` value is a monotonically increasing integer used to
remember optional dismissals. Never reuse a lower build for a newer release.
The user-facing download page may route visitors to Windows, macOS, Linux, or
Android packages, so it can remain the same stable URL for both channels.
