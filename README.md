# Moonlight S3 Host

Windows 配套软件，用 JPEG 将选定显示器发送到 ESP32-S3 RGB 触屏，并接收触摸控制。
对应固件：`C:\Users\10145294\Documents\PlatformIO\Projects\Moonlight_S3`。

## 启动

直接运行 `dist\MoonlightS3Host\MoonlightS3Host.exe`（保留旁边 `_internal` 整个目录）。
打包目录内的 `settings.json` 已配置为本机固件的配对码，不要将它当作公开示例上传。
也可运行源码 `python main.py` 或双击 `start.cmd`。

1. S3 烧录后，电脑连接 `Moonlight-S3` 热点，密码 `MoonlightS3`。
2. 软件填写 IP `192.168.4.1`、端口 `47989`、相同的 32 字符配对码。
3. 选择显示器、400×240 或 800×480、FPS、JPEG 质量，点“开始串流”。
4. 触屏操作栏提供 LEFT 左键、RIGHT 右键、SCROLL 滚轮和 KEYBOARD 系统屏幕键盘。
   在桌面区域按住移动可拖动；滚轮模式上下划动。切换按钮不向电脑桌面点击。
5. 点“停止 / 释放鼠标”即可结束；断线和触摸心跳超时也会释放按键。

关闭“允许触屏控制电脑”可以仅投屏；此时工具栏仅显示，无操作效果，可同时关闭工具栏。
开始前不会抓取桌面；程序不录屏、不上传第三方、不自动设置防火墙、不监听公网端口。
主机帧内绘制可见鼠标箭头；它是位置标记，不保证与 Windows 每种自定义光标形状一致。

S3 也支持在固件中配置路由器 STA 模式，届时填写 S3 在路由器中的地址。
主机支持 Windows 多显示器、负坐标和 DPI 感知；比例保留，黑边不触发点击。
运行期间配置锁定，要修改参数先停止。

## 性能含义

默认 400×240 / 25FPS / quality60，S3 放大显示到800×480。
800×480 档更清晰，但 S3 软件 JPEG 解码速度可能达不到20FPS。
面板默认12MHz扫描约25.36Hz，主机目标30FPS不会提高这个上限。
实际性能必须烧录后测量；GUI显示接收端确认的帧率、解码耗时、显示处理耗时、帧确认时延。
两帧在途上限用于避免持续累积延迟，差网络仍受 TCP 重传影响。

这是独立 JPEG 协议，不是 Moonlight/Sunshine 客户端，没有音频或公网中继。
需访问云主机时，应让 S3 与 Windows 主机通过本地网络或自备 VPN 可路由互通。
协议未加密，仅供可信网络。Windows SendInput 受 UIPI 限制：普通权限不能操作高权限窗口/UAC 安全桌面。
系统键盘依赖 Windows 的 osk.exe；本次未实际点击或启动它。

## 构建和测试

本机复用现有 Python 3.12，不创建 venv。依赖已经存在，精确版本在 `requirements.txt`。
另一台开发电脑缺依赖时可在其已有环境中运行 `python -m pip install -r requirements.txt`。

```powershell
python -m unittest discover -s tests -v
python main.py --gui-smoke
.\build.ps1
```

先运行上述测试命令，再用 `build.ps1` 通过 PyInstaller 生成 Windows onedir 软件。
打包软件自带 Python runtime，使用者不需要安装 Python；这不是另建开发虚拟环境。
`--gui-smoke` 只创建界面后退出，不连接 S3，不捕获或控制桌面。

测试通过 loopback 模拟 S3，与虚拟鼠标验证协议和安全释放，不会移动真实鼠标。
完整硬件测试尚未进行，未证明实际解码帧率、颜色、触摸坐标或操作系统输入效果。

协议文档在固件工程 `docs\PROTOCOL.md`。
第三方组件和许可证见 `THIRD_PARTY_NOTICES.md` 与打包目录 `licenses`。
