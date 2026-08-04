# Miaomiao / Orange 预发布交接验收

更新时间：2026-08-03（UTC）

## 1. 输入与基线

任务开始时工作区根目录不存在 `HANDOFF-ORANGE.md`；本文件根据 `HANDOFF.md`、三个
Miaomiao 仓库的 README/AGENTS/Actions 工作流和 `Orange-source` 补建，作为统一验收入口。

| 范围 | 已核对基线 | 预发布实现 |
| --- | --- | --- |
| Android | `main` `3c613726` | `handoff/orange-pre-release` / `55a5cc13` |
| Desktop | `main` `fdf13412` | `handoff/orange-pre-release` / `d85f77d7` |
| Config | `main` `2b88740` | 本文件所在交接分支 |
| Orange | 交接说明称 `8e9e4eb` | `Orange-source` 快照；远端仓库当前不可访问 |

`Orange-source` 不含 `.git`，三个 gitlink 子模块目录均为空，符合“仅 Git 跟踪文件”快照
的描述，但不能在没有原仓库递归检出的情况下独立重建。其源码与截图用于核对 XBoard
邀请、公告行为和 Orange 品牌图标。

## 2. 已完成

### Android

- 邀请码读取与单次生成、注册链接编码、复制、二维码和系统分享；生成结果不确定时不盲目重试。
- 普通公告启动提示，按正整数公告 `id` 持久去重，并让迁移公告/客户端更新保持更高优先级。
- 签名清单刷新增加 45 秒总预算与 20 秒单请求上限，同时保留“最高版本、同版本首镜像”策略。
- 业务 API 按内核明确选择 Xray SOCKS 入站或 sing-box HTTP 入站，不再把 10808 SOCKS 当 HTTP。
- Orange legacy/round/adaptive launcher 图标、可重复生成脚本、哈希/尺寸校验和 CI 审核素材。

### Desktop

- 所有镜像响应中稳定选择最高清单版本，同版本保留首镜像优先级。
- 客户端更新 URL 无效时回退签名清单下载页；工具页增加核心更新和客户端下载入口。
- 登录 token 以运行时随机 AES-GCM 密钥持久化，Unix 文件限制为当前用户读写；退出或 401 清除会话。
- Windows 主图标及四种托盘状态、macOS ICNS、Linux PNG、生成/校验脚本和 CI 审核素材。

### Config / CI

- Config payload v3、发布脚本和 15 项测试已做只读本地验证；未改 payload，未触发签名或生产部署。
- Android PR CI 校验图标、运行单测并构建 unsigned verification APK。
- Desktop PR CI 校验图标、运行服务测试，并编译 Windows/macOS/Linux；正式 release validate 也校验图标。
- 普通 CI 上传 Orange 图标审核素材，保留 14 天；正式签名、Tag 和 Release 路径保持手动授权。

## 3. 本地验收

- Android：Playstore Debug 主源码/资源编译成功；83 项单测全部通过；图标哈希/尺寸与 ShellCheck 通过。
- Desktop：93 项服务测试全部通过；Linux x64 自包含主程序与 Helper 编译成功；图标与 ShellCheck 通过。
- Config：15 项 Python 测试、payload v3 校验、`bash -n` 与 ShellCheck 全部通过。
- 三仓库工作流均可由 PyYAML 解析；所有提交前 `git diff --check` 通过。

## 4. 远端验收与产物

| 范围 | PR | 本次 Actions | 基线 Actions |
| --- | --- | --- | --- |
| Android | [#2](https://github.com/rmomo5285-droid/Miaomiao-Android/pull/2) | [30840949815](https://github.com/rmomo5285-droid/Miaomiao-Android/actions/runs/30840949815) 成功 | [30832857654](https://github.com/rmomo5285-droid/Miaomiao-Android/actions/runs/30832857654) 成功 |
| Desktop | [#1](https://github.com/rmomo5285-droid/Miaomiao-Desktop/pull/1) | [30840948641](https://github.com/rmomo5285-droid/Miaomiao-Desktop/actions/runs/30840948641) 成功 | [30802372206](https://github.com/rmomo5285-droid/Miaomiao-Desktop/actions/runs/30802372206) 成功 |
| Config | [#1](https://github.com/rmomo5285-droid/Miaomiao-Config/pull/1) | 文档路径不触发 publish | [30812570146](https://github.com/rmomo5285-droid/Miaomiao-Config/actions/runs/30812570146) 与 [Pages 30812589927](https://github.com/rmomo5285-droid/Miaomiao-Config/actions/runs/30812589927) 成功 |

Android Actions 完成图标校验、单测和 unsigned verification APK 组装，但按预发布策略不上传或发布
正式 APK。Android/Desktop 图标审核 artifact 分别为 `miaomiao-android-orange-icon-review` 和
`miaomiao-desktop-orange-icon-review`，已下载到工作区 `handoff-artifacts/`。

## 5. 尚未跨越的发布门槛

- 不创建 Tag/Release，不运行 Android 手动签名构建或 Desktop release workflow，不发布正式安装包。
- 不读取或验证仓库 Secret 内容；Android 签名、Windows Authenticode、macOS Developer ID/公证和 GPG
  只能在获得发布授权且外部 Secret 已配置后验收。
- 需要在真实 Android、Windows、macOS 和 Linux 设备上审核 launcher、任务栏/托盘、窗口和安装包图标。
- 仍缺不同主域名、不同托管商的独立只读 bootstrap mirror；这需要外部域名/托管资源。
- `sanrokamlan-prog/Orange` 当前对现有 GitHub 身份返回 Not Found，无法核对 `8e9e4eb` 或远端 Actions；
  `Orange-source` 又没有 gitlink 提交元数据，需恢复仓库访问后复核。

正式发布前先完成 PR 审查与合并、设备视觉审核、独立镜像和 Secret/签名身份确认，再由负责人明确授权发布。
