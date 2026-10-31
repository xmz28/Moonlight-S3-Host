# Windows 端发布说明

Windows 端与 S3 固件使用两个独立公开源码仓库：[Windows 端](https://github.com/xmz28/Moonlight-S3-Host)、[S3 固件](https://github.com/xmz28/Moonlight-S3)。协议以固件仓库的 `docs/PROTOCOL.md`、`docs/PAIRING.md` 为准，正式 Release 链接到配套 tag，避免链接到持续变化的开发分支。

## 构建

使用 Python 3.12 及 requirements.txt 中的依赖。先执行软件测试、GUI smoke，再运行 `./build.ps1`。公开构建使用 `dist-release/` 和 `build/release/`，原开发版 `dist/` 及本机授权不受影响。

产物：

- `dist-release/MoonlightS3Host-windows.zip`：完整 onedir 程序、README、第三方声明、licenses 和 SOURCE.txt。
- `dist-release/SHA256SUMS.txt`：ZIP 的 SHA-256。

`tools/package_release.py` 在打包前去除独立发布目录顶层的 settings.json，并拒绝包含嵌套本机配置的目录。它不会读取或修改源码目录和原开发版的 settings.json。首次无固定配置时才生成电脑身份；首次迁移程序旁旧配置并保留原文件，之后换解压目录也复用身份。旧用户升级前从托盘退出并保留 `%LOCALAPPDATA%\MoonlightS3Host\settings.json`。

SOURCE.txt 记录构建时的 HEAD 和工作区是否有修改。本轮整理阶段生成的包仅供审核，不是精确对应某个干净提交的正式发布包。提交后应从干净 tag 重建、校验并补充配套固件版本，然后才上传 Release。

## 版本与许可

每次 Release 记录本仓库 tag/提交、配套固件 tag/提交、MS3 v3 会话控制 / v2 PIN 授权 / v1 JPEG 帧协议、支持的硬件、软件测试与实机验证范围。2026-10-31 当前源码基线为电脑端 `f2bbff2`、固件 `5dfb457`，两端需同步更新，并支持 PAK3 菜单暂停确认。

本次同步包含已提交的 v3 连接、单点操作、后台托盘、菜单暂停及电脑界面精简源码；本轮新增修改集中在文档和发布元数据。历史性能和用户验收见固件仓库文档；本轮验证另行记录，不能把历史结果写成本轮实机验收。

当前自有代码尚未选定顶层 LICENSE，后续单独确认；保留现有第三方声明和 licenses。两个公开源码仓库互相链接，二进制 Release 单独发布。用户已确认本轮修改并授权提交 GitHub；v0.1.0同时提供免编译二进制附件，并设为Latest。

## 当前升级检查

确认 SOURCE.txt 记录 v3 会话控制、v2 PIN 与 v1 JPEG；检查 ZIP 不含本机配置、凭据和诊断日志。GUI smoke 不改写配置；协议、菜单暂停及身份迁移使用软件测试验证。配套固件新增独立配置分区，旧布局不能只刷应用，迁移方法见固件发布说明。历史实机验收与本轮仓库检查分别记录，不将旧性能数字写成本轮新实测。

## v0.1.0 配套下载

[固件 Latest](https://github.com/xmz28/Moonlight-S3/releases/latest) · [Windows Latest](https://github.com/xmz28/Moonlight-S3-Host/releases/latest)。两个仓库均使用v0.1.0标签并记录精确源码提交，附件包括中文安装说明、来源与哈希。发布验证不包含本次重新烧录或新增性能实测。
