# 更新记录

## 2026-10-30：双仓库发布准备

- 公开包输出到独立 dist-release，保留源码目录与原 dist 开发版的本机配置。
- 不再把本机 settings.json、电脑身份和配对凭据复制到公开软件；首次运行生成配置，原用户覆盖升级保留自己的配置。
- 新增 ZIP 打包、SOURCE.txt、SHA256SUMS.txt、嵌套配置拒绝检查，以及两个发布隔离测试。
- 更新 README、独立仓库构建/升级及发布说明，建立两个公开源码仓库并互链；自有代码 LICENSE 尚未选定。
- 39 项软件测试、源码 GUI smoke、PyInstaller 完整构建和打包 exe GUI smoke通过；实际 ZIP 内容和 SHA-256 校验通过，未包含 settings.json 或已知本机身份/凭据字节。PyInstaller 的两个 macOS framework 探测警告来自 pySerial 非 Windows 平台代码，Windows 打包及 GUI smoke 成功。
- 本轮未烧录、未重新进行真实串流/触控和长期性能测试；历史实机结果由固件仓库维护。用户已确认提交并授权上传公开源码。
