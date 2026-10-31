# Moonlight S3 Host v0.1.0 免编译安装

适用于 Windows x64；无需安装 Python、依赖或编译源码。需配套 [Moonlight-S3 v0.1.0 固件](https://github.com/xmz28/Moonlight-S3/releases/tag/v0.1.0)。

1. 下载 MoonlightS3Host-windows-v0.1.0.zip，完整解压到可写目录。
2. 双击 MoonlightS3Host.exe，保留旁边 _internal 文件夹；程序及依赖必须一起使用。
3. 在 S3 屏幕上设置2.4 GHz Wi-Fi，电脑通过有线或Wi-Fi进入可互通局域网。
4. S3 首页点选电脑，首次把屏上四位 PIN 输入电脑弹窗，配对成功自动开始。之后保留授权即可直接连接。

软件从 GitHub 下载后可能显示系统下载来源提示；此版本未做发行者代码签名，请核对下载仓库及 SHA256SUMS.txt。可在 PowerShell 执行 `Get-FileHash .\MoonlightS3Host-windows-v0.1.0.zip -Algorithm SHA256` 比较校验值。

## 升级和配置

先从托盘退出旧程序，再解压新版。不要删除 `%LOCALAPPDATA%\MoonlightS3Host`，其中 settings.json 保存身份及授权，diagnostics.log 保存轮换诊断记录。第一次升级会迁移程序旁旧配置并保留原文件，之后更换解压目录仍复用身份。公开包不包含这些本机文件。

关闭主窗口会收起到托盘继续待命，退出请用托盘或“更多→退出软件”。开机后台运行默认关闭，可在设置中启用。界面不提供手填IP、电脑端开始或USB配网按钮；S3负责发起连接，地址按设备身份自动更新。

## 操作和限制

画质、显示器、输入模式等在 S3 上设置，“保存并返回”写入，点击“继续桌面”应用；画面参数变化时可能自动重连。MENU暂停、BACK返回，支持单点触摸/触摸板、长按右键、滚轮、快捷键和ASCII文字输入。没有中文输入法、音频、剪贴板、文件传输或公网中继；流数据仍未加密，仅用于可信网络。

源码功能已有历史实机验收；本次公开包进行软件回归、打包和GUI启动检查，未重新跑真实串流性能及长期稳定性测试。完整说明见README.md，源码信息见SOURCE.txt，第三方声明及许可证随包保留。
