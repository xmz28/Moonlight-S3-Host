# Moonlight S3 Host

Windows 配套软件，用 JPEG 将选定显示器发送到 ESP32-S3 RGB 触屏，并接收触摸控制。
对应固件：`C:\Users\10145294\Documents\PlatformIO\Projects\Moonlight_S3`。

## 启动

直接运行 `dist\MoonlightS3Host\MoonlightS3Host.exe`（保留旁边 `_internal` 整个目录）。
打包目录内的 `settings.json` 已配置为本机固件的配对码，不要将它当作公开示例上传。
也可运行源码 `python main.py` 或双击 `start.cmd`。

1. S3 烧录后，点击“首次配置 S3 Wi-Fi（USB）”，选择设备串口，保存路由器的2.4GHz Wi-Fi。
   工具识别Moonlight S3固件后才发送配置，保存到板内NVS并重启，不烧录。以后不需要USB连接。
2. 电脑通过有线或Wi-Fi接入同一局域网，点击“搜索局域网”，从列表选择接收端；IP和端口自动填入。
   使用与固件相同的32字符配对码。设备名称相同时按完整唯一ID区分，不会自动连接第一个发现结果。
3. 选择显示器、400×240 或 800×480、FPS、JPEG 质量，点“开始串流”。
4. 触屏操作栏提供 LEFT 左键、RIGHT 右键、SCROLL 滚轮、KEYBOARD 系统屏幕键盘和 BACK 返回首页。
   在桌面区域按住移动可拖动；滚轮模式上下划动。切换按钮不向电脑桌面点击。
5. 点“停止 / 释放鼠标”即可结束；断线和触摸心跳超时也会释放按键。

关闭“允许触屏控制电脑”可以仅投屏；此时 LEFT/RIGHT/SCROLL/KEYBOARD 不注入输入，BACK 仍能停止并返回首页；可关闭工具栏后改用电脑停止。
开始前不会抓取桌面；程序不录屏、不上传第三方、不自动设置防火墙、不监听公网端口。
主机帧内绘制可见鼠标箭头；它是位置标记，不保证与 Windows 每种自定义光标形状一致。

S3 仅使用路由器 STA 模式，不开热点，连接失败也不退回热点；断线自动重连。
电脑可用5GHz Wi-Fi或有线，只需与S3所在网络互通。配置工具不保存或输出Wi-Fi密码。
如果不方便USB配置，可在固件的本地 `config_secrets.h` 中设置路由器SSID/密码后编译。
UDP47990用于局域网发现，TCP47989用于串流。发现失败时可直接填写屏幕上的IP，
或设备的 `moonlight-s3-xxxxxx.local` 主机名（需要电脑支持mDNS）。
访客Wi-Fi客户端隔离、跨子网广播限制或防火墙可能阻止搜索；程序不会自动修改防火墙。
主机支持 Windows 多显示器、负坐标和 DPI 感知；比例保留，黑边不触发点击。
运行期间配置锁定，要修改参数先停止。

## 性能含义

默认 400×240 / 25FPS / quality60，S3 放大显示到800×480。
电脑优先使用 DXGI 桌面复制；先缩小 BGRA 像素，再在小图上转换颜色、画工具栏和编码 JPEG。
DXGI 不可用时依次回退到 GDI 缩放抓屏和 MSS；界面会显示实际使用的抓屏方式。
多显示器通过完整桌面坐标匹配，不能匹配时回退，不猜测显示器编号。
800×480 档更清晰，但 S3 软件 JPEG 解码速度可能达不到20FPS。
面板默认12MHz扫描约25.36Hz，主机目标30FPS不会提高这个上限。
实际性能必须烧录后测量；GUI显示接收端确认的帧率、解码耗时、显示处理耗时、帧确认时延。
默认开启“流畅优先”，最多三帧在途以填满处理管线；关闭后最多两帧，减少排队。
两种模式都只在有空位时捕获新屏幕，不持续积累截图队列；差网络仍受 TCP 重传影响。

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
python main.py --capture-smoke
.\build.ps1
```

先运行上述测试命令，再用 `build.ps1` 通过 PyInstaller 生成 Windows onedir 软件。
打包软件自带 Python runtime，使用者不需要安装 Python；这不是另建开发虚拟环境。
`--gui-smoke` 只创建界面后退出，不连接 S3，不捕获或控制桌面。
`--capture-smoke` 实际验证 DXGI 抓屏及 JPEG 编码，不保存图像、不连接 S3、不注入输入。
显式实机基准：`python tools/benchmark_stream.py --serial COM17 --output build/benchmark.json`。
该命令使用真实桌面、quality60、目标25FPS，默认每档25秒，并关闭触摸控制。输出不包含配对码。

测试通过 loopback 模拟 S3，与虚拟鼠标验证协议和安全释放，不会移动真实鼠标。
发现测试用本机UDP模拟回复；配网测试使用虚拟串口对象，不打开实际串口。
已完成实际投屏、基本触摸回传和 Windows 控制，用户确认画面/操作正常。
逐阶段性能记录位于固件工程 `docs/PERFORMANCE.md`；未逐项验证的操作和长期稳定性见 `docs/BUILD_REPORT.md`。

协议文档在固件工程 `docs\PROTOCOL.md`。
第三方组件和许可证见 `THIRD_PARTY_NOTICES.md` 与打包目录 `licenses`。

## 2026-10-30 已验证版本

界面改动前保存当前版本：默认流畅优先，400×240实测22.709 FPS、800×480实测11.688 FPS。
23项软件测试与12项实机恢复检查通过；用户确认画面与触摸正常。
性能记录在固件项目 `docs/PERFORMANCE.md`。本机Wi-Fi密码、配对码和settings.json不纳入Git。


## S3 首页启动与返回

电脑软件保持打开、选好接收端和配对码后，可在 S3 首页点“开始串流”。软件空闲时每秒通过原 UDP47990 向选定设备发送带随机数和 HMAC 的单播查询，串流时停止查询。无需电脑新增监听端口。请求15秒超时，软件未打开时不会启动。

底栏五个按钮各160逻辑像素宽，最右侧 BACK 停止连接、释放鼠标并返回 S3 首页。用户已确认开始和返回均正常。新版通过27项软件测试、打包 GUI 与实际抓屏 smoke 检查。S3 的 Wi-Fi 扫描和密码输入现在也可在屏上完成，USB 配网仍可使用。

## 首次随机码配对改造前存档

保存当前已验证的 S3 屏上开始、BACK 返回、只读模式返回和签名启动查询。当前配对依赖双方配置一致的固定32字符密钥；接下来改造为屏上四位随机码首次授权及后续自动验证。
