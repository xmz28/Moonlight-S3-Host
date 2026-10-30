# Moonlight S3 Host

Windows 配套软件，用 JPEG 将选定显示器发送到 ESP32-S3 RGB 触屏，并接收触摸控制。
对应固件：`C:\Users\10145294\Documents\PlatformIO\Projects\Moonlight_S3`。

## 启动

直接运行 `dist\MoonlightS3Host\MoonlightS3Host.exe`（保留旁边 `_internal` 整个目录）。
`settings.json` 保存本机参数及配对后的授权凭据，不要作为公开示例上传。旧固定密钥已停用；上一版四位码配对会迁移保留。
也可运行源码 `python main.py` 或双击 `start.cmd`。

1. 电脑软件保持打开；两端接入同一局域网。S3的Wi-Fi可在屏上设置，也可使用USB配网。
2. 在 S3 首页扫描并点击电脑。已配对直接串流；首次需要配对时，电脑自动弹出PIN窗口。
3. 在电脑输入 S3 显示的四位 PIN，验证后自动开始；下次不再输入。
4. 底栏 LEFT / RIGHT / SCROLL / KEYBOARD 操作电脑，BACK 返回电脑列表。
5. 查看或删除授权统一在“已配对设备”。任一端删除后，下次串流自动进入首次配对。

不再提供手动配对按钮、配对开关或长密钥输入框。电脑仍保留画面参数、停止/释放鼠标和手动接收端选择作为备用；S3发起时自动选中对应接收端。

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


## 自动配对与设备管理

S3列表通过电脑公告检查双端配对状态，按完整身份区分同名设备。首次从S3点选电脑，电脑自动弹窗输入PIN；配对成功自动串流。已有配对直接启动；BACK回到列表。S3保存最多四台电脑，电脑可保存多个S3；管理页删除某一台不影响其他授权。

电脑使用稳定computer_id，已有四位码凭据会迁移保留。授权仍保存在忽略的settings.json；源代码与打包目录各有本机配置。37项软件测试及打包GUI smoke通过，用户已确认电脑列表、直接串流、返回、删除后首次状态及自动弹窗/串流全部正常。设备协议和边界见固件docs/PAIRING.md。


## 自动验证和防重放

首次PIN授权后，双方保存会话派生的长期密钥。每次连接由S3生成新的32-byte随机挑战，电脑用HMAC-SHA256返回证明，S3也向电脑返回另一方向的证明；长期密钥不直接发送。旧认证报文不能直接拿到新连接重放。原理、实机历史记录和完整边界见固件docs/PAIRING.md。

此处防护针对认证握手；当前JPEG/触控仍未加密和逐报文认证，不能据此防实时中间人转发或业务数据篡改/重放。本机settings.json保存的凭据未加密，不纳入Git。

2026-10-30：以上功能与文档随中文提交归档，软件测试及实机确认范围见固件docs/BUILD_REPORT.md。
