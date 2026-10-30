# Windows 端发布说明

Windows 端与 S3 固件使用两个独立公开源码仓库：[Windows 端](https://github.com/xmz28/Moonlight-S3-Host)、[S3 固件](https://github.com/xmz28/Moonlight-S3)。协议以固件仓库的 `docs/PROTOCOL.md`、`docs/PAIRING.md` 为准，正式 Release 链接到配套 tag，避免链接到持续变化的开发分支。

## 构建

使用 Python 3.12 及 requirements.txt 中的依赖。先执行软件测试、GUI smoke，再运行 `./build.ps1`。公开构建使用 `dist-release/` 和 `build/release/`，原开发版 `dist/` 及本机授权不受影响。

产物：

- `dist-release/MoonlightS3Host-windows.zip`：完整 onedir 程序、README、第三方声明、licenses 和 SOURCE.txt。
- `dist-release/SHA256SUMS.txt`：ZIP 的 SHA-256。

`tools/package_release.py` 在打包前去除独立发布目录顶层的 settings.json，并拒绝包含嵌套本机配置的目录。它不会读取或修改源码目录和原开发版的 settings.json。首次运行生成自己的电脑身份，首次连接重新配对；旧用户覆盖升级时保留自己的 settings.json。

SOURCE.txt 记录构建时的 HEAD 和工作区是否有修改。本轮整理阶段生成的包仅供审核，不是精确对应某个干净提交的正式发布包。提交后应从干净 tag 重建、校验并补充配套固件版本，然后才上传 Release。

## 版本与许可

每次 Release 记录本仓库 tag/提交、配套固件 tag/提交、MS3 v2 授权 / v1 JPEG 帧协议、支持的硬件、软件测试与实机验证范围。当前整理前基线为电脑端 `46578a6`、固件 `6207156`。

本轮仅修改构建、发布工具和文档，未改变 Windows 抓屏、串流、授权或输入控制逻辑。历史性能和用户验收见固件仓库文档；本轮验证另行记录，不能把历史结果写成本轮实机验收。

当前自有代码尚未选定顶层 LICENSE，后续单独确认；保留现有第三方声明和 licenses。两个公开源码仓库互相链接，二进制 Release 单独发布。用户已确认本轮修改并授权提交 GitHub；本次上传源码，二进制 Release 另行发布。
