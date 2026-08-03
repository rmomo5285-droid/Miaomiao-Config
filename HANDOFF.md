# 喵喵客户端项目交接文档

更新时间：2026-08-04（Asia/Shanghai）

## 1. 仓库与当前基线

| 组件 | GitHub 仓库 | 当前基线 |
| --- | --- | --- |
| Android | `rmomo5285-droid/Miaomiao-Android` | `3c613726`，版本 `2.3.3` / build `743` |
| Windows / macOS / Linux | `rmomo5285-droid/Miaomiao-Desktop` | `fdf13412` |
| 远程配置 | `rmomo5285-droid/Miaomiao-Config` | 以本文件所在的 `main` 为准 |
| Orange 原项目 | `sanrokamlan-prog/Orange` | `8e9e4eb` |

本次 Android 待交付改动：

- `c22e8c20`：多个签名清单镜像同时可用时选择 `version` 最高的清单；相同版本保留优先镜像。
- `3c613726`：Android 版本由 `2.3.2/742` 更新到 `2.3.3/743`。

Desktop 和 Config 在编写本文件前已经与各自 `origin/main` 一致。

## 2. 已实现能力

Android 与 Desktop 已接入：

- 喵喵/XBoard 登录、注册、套餐购买和支付入口。
- 登录后自动取得托管订阅，默认每 48 小时更新；失败时保留本地节点。
- ECDSA P-256 签名远程清单，用于热切换 API、注册页、下载页和迁移公告。
- 客户端版本更新提示；内核更新继续使用上游来源。
- 默认 TUN MTU `1280`。
- Android 使用固定的 AndroidLibXrayLite；Desktop 的 Hysteria2 节点固定选择 sing-box。
- GitHub Actions 构建 Android、Windows、macOS 和 Linux，不依赖本机打正式包。

## 3. 线上配置

当前 `manifest.payload.json`：

- 清单版本：`3`
- 主 API：`https://www.miaonetwork.com`
- 备用 API：`https://www.vpnmiao.com`
- 注册页：`https://www.miaonetwork.com/#/register`
- 下载页：`https://download.vpnmiao.com/download/index.html`
- 主清单：`https://cdn.vpnmiao.com/manifest.json`
- 兼容地址：`https://cdn.vpnmiao.com/json`

切换品牌入口或新域名时，只修改 `manifest.payload.json`：

1. 递增顶层 `version`。
2. 修改 `apiEndpoints`、`registrationUrl`、`downloadPageUrl`。
3. 如需迁移弹窗，填写 `migrationNotice`，并使用新的唯一 `id`。
4. 如需客户端更新提示，填写 `updates.android` 与 `updates.desktop`，下载地址必须已经可用。
5. 提交到 `main`；`publish.yml` 负责签名、发布和 VPS/CDN 验证。

不要把私钥、口令或 GitHub Token 写进仓库。Actions 仅引用以下 Secret 名称：

- `MIAOMIAO_MANIFEST_PRIVATE_KEY`
- `MIAOMIAO_MANIFEST_KEY_PASSPHRASE`
- Android / Desktop 发布签名与 GPG Secret
- 可选的 Cloudflare 和 VPS 部署 Secret（详见 `README.md`）

## 4. 构建与发布

### Android

推送 `main` 会运行普通 CI；正式发布需要手动运行 `build.yml`，并填写：

```text
release_tag=v2.3.3
```

工作流输出 arm64-v8a、armeabi-v7a、x86、x86_64 和 universal APK。推送代码本身不会自动创建正式 Release。

### Desktop

正式包通过 `release-desktop.yml` 构建 Windows ZIP、macOS DMG、Linux DEB/RPM。发布前必须确认代码签名、公证和 GPG Secret 已配置；不要在本机提交签名私钥。

### Config

```powershell
gh workflow run publish.yml --repo rmomo5285-droid/Miaomiao-Config
gh run list --repo rmomo5285-droid/Miaomiao-Config --workflow publish.yml --limit 5
```

## 5. Orange 源码与图标决定

最终决定继续使用 Orange 原版图标，不采用本地生成的纸飞机概念稿。原始资源：

```text
G:\Orange-main\assets\images\icon.png
G:\Orange-main\assets\images\icon.ico
```

图标尚未写入 Android / Desktop 仓库。下一步需要从原图生成并核对 Android mipmap、Windows ICO、macOS ICNS 和 Linux PNG；完成视觉审核后再触发正式打包。

Orange 的干净源码交接包由 `sanrokamlan-prog/Orange` 的 `8e9e4eb` 生成，存放在：

```text
G:\Orange-build\handoff\Orange-source-8e9e4eb.zip
```

该压缩包只包含 Git 跟踪源码，不包含 `.git`、缓存、构建产物或密钥。`G:\Orange-main` 和 `G:\Orange-push` 原目录不会被删除或移动。

## 6. 已知待办与风险

- Android 本地测试未运行：当前机器没有 Java/JDK。提交后以 GitHub Actions 结果为准。
- Android 新的镜像选择会扫描全部镜像以取得最高版本；网络极差时刷新耗时可能增长，后续应增加整体超时或并发请求。
- Android 的 `10808` 代理协议需要再次核对：业务 API 必须使用真实 HTTP 入口或明确使用 SOCKS，不能把 SOCKS 端口当 HTTP 代理。
- Android 仍需补齐邀请分享页，以及普通公告的一次性启动弹窗和按公告 `id` 去重。
- Desktop 仍需把清单镜像选择统一为“最高版本”，补齐下载页兜底、核心更新主入口和登录状态持久化。
- 五端 UI、Orange 图标替换和安装包签名尚未完成；当前不应发布正式版。
- `cdn.vpnmiao.com` 与 GitHub 回退都不构成完全独立的抗封锁路径，仍建议增加一个不同主域名、不同托管商的只读清单镜像。

## 7. 换机后快速核对

```powershell
gh auth status
git clone https://github.com/rmomo5285-droid/Miaomiao-Android.git
git clone https://github.com/rmomo5285-droid/Miaomiao-Desktop.git
git clone https://github.com/rmomo5285-droid/Miaomiao-Config.git
gh run list --repo rmomo5285-droid/Miaomiao-Android --limit 5
gh run list --repo rmomo5285-droid/Miaomiao-Desktop --limit 5
gh run list --repo rmomo5285-droid/Miaomiao-Config --limit 5
```

换机后先等待三个仓库最新 Actions 完成，再继续图标替换和正式发布。
