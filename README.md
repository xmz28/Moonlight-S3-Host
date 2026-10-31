# Moonlight S3 Host

## 免编译下载（v0.1.0）

[下载最新 Windows 软件（Latest）](https://github.com/xmz28/Moonlight-S3-Host/releases/latest) · [配套 S3 固件（Latest）](https://github.com/xmz28/Moonlight-S3/releases/latest)

下载 `MoonlightS3Host-windows-v0.1.0.zip`，完整解压到可写目录，双击 `MoonlightS3Host.exe`；保留 `_internal` 文件夹。适用于 Windows x64，无需安装 Python 或重新编译。不要把 GitHub 自动生成的 Source code ZIP 当作可运行软件。首次连接仍需在 S3 上选择电脑并输入 PIN。

升级前先从托盘退出旧程序，保留 `%LOCALAPPDATA%\MoonlightS3Host` 配置目录；换解压目录不改变电脑身份。v0.1.0 需配套同版本 S3 固件，详细说明见 [免编译安装说明](INSTALL.zh-CN.md)。

Windows 配套软件，将选定显示器编码为 JPEG，发送到 ESP32-S3 RGB 触屏，并接收单点触摸、快捷键和文字输入。

[Windows 源码仓库](https://github.com/xmz28/Moonlight-S3-Host) · [S3 固件仓库](https://github.com/xmz28/Moonlight-S3) · [更新记录](CHANGELOG.md) · [构建与发布](RELEASING.md)

## 当前版本与配套要求

2026-10-31 源码基线：电脑端 `f2bbff2`、固件 `5dfb457`。当前使用 **MS3 v3 会话控制 / v2 PIN 授权 / v1 JPEG 帧格式**，菜单暂停需两端共同支持 PAK3 确认。升级时请同步更新两端。

这是独立 JPEG 串流项目，不兼容 Moonlight/Sunshine 的 GameStream 协议；没有音频、剪贴板、文件传输或公网中继。本次同步源码，不代表已发布二进制 Release。

## 启动与连接

本机构建运行 `dist-release/MoonlightS3Host/MoonlightS3Host.exe`，完整 ZIP 为 `dist-release/MoonlightS3Host-windows.zip`；解压时保留 `_internal` 整个目录。源码可运行 `python main.py` 或 `start.cmd`。原 `dist/` 是本机开发软件目录，构建不会覆盖它。

1. 在 S3 首页“Wi-Fi 设置”扫描并连接 2.4 GHz 路由器；电脑通过有线或 Wi-Fi 接入可互通的局域网。
2. 打开电脑软件，在 S3 首页选择电脑。已配对直接连接；首次 S3 显示四位 PIN，电脑自动弹窗，输入成功后自动开始。
3. 电脑主界面分别显示连接状态、当前接收端和会话统计；取消 PIN 或在 S3 返回会取消对应请求，迟到请求不能启动串流。
4. S3 的每台电脑设置保存显示器、分辨率、画质、FPS、底栏、控制权限、输入模式和性能浮窗。点击选项仅暂存，“保存并返回”才写入；从串流菜单保存后，点击“继续桌面”应用，必要时自动重连。
5. BACK 返回电脑列表；MENU 打开本地菜单，可继续、重连、断开或调整设置。电脑软件保持待命，断开投屏不会关闭电脑上的应用。

电脑主界面提供“已配对设备”“设置”和“更多”。设置窗口包含开机后台运行、流畅优先；更多提供只读诊断、日志入口和退出。手填 IP、TCP 端口编辑、接收端搜索列表、电脑端开始按钮与 USB 配网按钮已移除，自动发现及严格身份绑定保留。USB 配网底层源码工具仍在 `wifi_setup.py`。

关闭主窗口收起到系统托盘；托盘可重新打开或真正退出。开机后台运行默认关闭。每个 Windows 登录会话只运行一个交互实例，再次打开激活现有窗口。

## 单点操作和菜单

- 直接触摸：轻点左键，移动拖动，停留约 0.6 秒右键。
- 单指触摸板：滑动移动指针，轻点左键，长按右键，快速第二次按住后移动拖动。
- SCROLL 单指上下划动滚轮；KEYBOARD 打开 S3 本地英文、数字与符号键盘，当前不含中文输入法。
- 六个底栏按键等宽，MENU 位于 BACK 右侧；隐藏底栏仍保留 MENU。菜单分为输入、画面与设置、快捷键、连接，右上角唯一“继续桌面”。
- MENU 快速输入模式和浮窗开关即时保存；设置页通过“保存并返回”统一保存。仅观看禁止鼠标、快捷键和文字注入，仍可退出本地菜单。

MENU 使用 PAU3/PAK3 暂停屏障：收完在途 JPEG 后再绘制菜单，期间不抓取新帧。心跳和统计与 JPEG 串行发送，支持部分写入与短超时重试，真实断线检测仍为 3 秒。断开或超时会释放按键。

## 配置、升级和诊断

本机身份、参数及配对凭据固定保存在 `%LOCALAPPDATA%\MoonlightS3Host\settings.json`，首次迁移程序旁旧配置并保留原文件。之后更换解压目录复用同一身份，无需因更新目录重新配对；只有授权删除、凭据丢失或身份变化才需重新授权。

更新程序前先从托盘退出；替换程序文件，保留上述固定目录及首次迁移需要的旧配置。配置原子写入，损坏文件不会被静默清空。轮换 `diagnostics.log` 位于同一目录，不记录 PIN、Wi-Fi 密码或长期凭据；不要将本机配置随公开包上传。

S3 重启或 DHCP 换地址后，电脑空闲时约每 4 秒重新发现设备；通过完整设备身份和原授权验证后更新地址，不需手填 IP。发现失败应检查同网段互通、访客 Wi-Fi 隔离及防火墙；程序不自动修改防火墙。UDP47990 用于发现，TCP47989 用于串流。

## 画质、统计与边界

默认 400×240 / 25 FPS / JPEG quality60，S3 放大到 800×480。优先 DXGI 桌面复制，不可用时回退 GDI 缩放抓屏、MSS；按完整桌面坐标匹配显示器，支持负坐标和 DPI 感知。

流畅优先最多三帧在途，关闭后两帧；有空位才抓取新画面，TCP 差网络仍可能重传排队。此选项串流期间锁定，下次连接生效。

可选 S3 本地性能浮窗显示显示 FPS、解码/显示耗时、ACK、JPEG 接收 Mbps 和信号强度。ACK 是帧处理确认耗时，不是 ping 或触摸总延迟；接收速率不是链路测速。开启时电脑每秒发送约 16 字节统计消息。12 MHz 面板扫描约 25.36 Hz，设置 30 FPS 不会提高此上限。

历史优化阶段测得 400×240 约 22.71 FPS、800×480 约 11.69 FPS；这是此前版本和测试场景的记录，新菜单及浮窗版本未重新跑标准性能基准。历史实机验收与未测范围见固件 [连接与操作](https://github.com/xmz28/Moonlight-S3/blob/main/docs/SESSION_UX.md)及[性能记录](https://github.com/xmz28/Moonlight-S3/blob/main/docs/PERFORMANCE.md)。

认证握手使用随机挑战和双向证明；JPEG/触控数据仍未加密及逐报文认证，仅用于可信网络。SendInput 受 Windows 权限与当前焦点限制，普通权限不能操作 UAC 安全桌面；本机配置未加密。程序不录屏、不上传第三方，开始串流前不抓取桌面。

## 构建与验证

Windows 使用 Python 3.12，依赖精确版本见 `requirements.txt`；缺少依赖时运行 `python -m pip install -r requirements.txt`。

```powershell
python -m unittest discover -s tests -v
python main.py --gui-smoke
python main.py --capture-smoke
.\build.ps1
```

GUI smoke 不连接 S3、不捕获桌面、不改写本机配置；capture smoke 实际抓屏及 JPEG 编码，不保存图像、不连接设备、不注入输入。自动测试使用 loopback、虚拟串口和鼠标，不等同本轮实机操作验收。

构建输出到独立 `dist-release/`，附中文说明、第三方许可证、SOURCE.txt 和 SHA256SUMS.txt，不含本机 settings.json。工作区有修改的包标为审核构建；正式 Release 应从干净 tag 重建并写明配套版本。本次没有发布二进制附件。

实机性能工具：`python tools/benchmark_stream.py --serial <串口> --output build/benchmark.json`。需先从托盘退出正常软件，再按提示在 S3 点选电脑授权；遵守 v3 请求门控。此命令会抓取真实桌面，不能作为普通软件测试自动执行。

协议见固件 [PROTOCOL.md](https://github.com/xmz28/Moonlight-S3/blob/main/docs/PROTOCOL.md)和[PAIRING.md](https://github.com/xmz28/Moonlight-S3/blob/main/docs/PAIRING.md)。第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 `licenses/`；自有代码尚未选定顶层 LICENSE。
