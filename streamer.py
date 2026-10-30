import socket
import threading
import time
from PIL import Image
import mss
from capture import DesktopCapture, ScaledCapture
from protocol import MESSAGE, MAX_JPEG, Viewport, content_geometry, encode_frame, frame_packet, recv_exact, token_bytes
from input_control import WindowsMouse, TouchController, SingleTouchController, cursor_position
from pairing import authenticate
from session_control import FIRST_FRAME,STREAMING

class StreamSession:
    def __init__(self, settings, report=lambda message: None, capture=None, mouse=None):
        self.settings = settings.copy()
        self.report = report
        self.capture_override, self.mouse_override = capture, mouse
        self.stop_event = threading.Event()
        self.socket = None
        self.pending = {}
        self.condition = threading.Condition()
        self.error = None
        self.sent = self.acked = self.failed = 0
        self.profile=dict(capture_ms=0.0,encode_ms=0.0,send_ms=0.0,frames=0,bytes=0)
        self.paused=threading.Event()
        self.overlay=threading.Event()
        if settings.get("stats",False):self.overlay.set()
        self.latest_ack_us=0
        self.pause_id=0

    def stop(self):
        self.stop_event.set()
        with self.condition: self.condition.notify_all()
        if self.socket:
            try: self.socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass

    def _send_packet(self,packet,label="发送数据"):
        """One writer, exact partial-write offsets; recv's 100ms timeout is not a send deadline."""
        view=memoryview(packet);deadline=time.monotonic()+3
        while view and not self.stop_event.is_set():
            try:
                count=self.socket.send(view)
                if not count:raise ConnectionError("发送连接断开")
                view=view[count:]
            except socket.timeout:
                if time.monotonic()>=deadline:raise TimeoutError(label+"超时")
            except OSError:
                if self.stop_event.is_set():return False
                raise
        return not view

    def _receive(self, controller):
        buffer = bytearray()
        last_touch = time.monotonic()
        last_report = time.monotonic()
        last_count = 0
        try:
            while not self.stop_event.is_set():
                try:
                    chunk = self.socket.recv(4096)
                except socket.timeout:
                    chunk = None
                if chunk == b"": raise ConnectionError("ESP32-S3 已断开")
                if chunk: buffer.extend(chunk)
                while len(buffer)>=MESSAGE.size:
                    tag,a,b,c = MESSAGE.unpack(buffer[:16])
                    if tag==b"TXT3":
                        if not 1<=a<=128:raise ValueError("文本长度无效")
                        if len(buffer)<16+a:break
                        value=bytes(buffer[16:16+a]).decode("utf-8");del buffer[:16+a]
                        if self.settings.get("control",True):controller.mouse.text(value)
                        continue
                    del buffer[:16]
                    if tag==b"TCH1":
                        if controller and not self.paused.is_set(): controller.update(a,b,c)
                        last_touch=time.monotonic()
                    elif tag==b"PAU3":
                        controller.release()
                        with self.condition:
                            if a:self.pause_id=b;self.paused.set()
                            else:self.paused.clear()
                            self.condition.notify_all()
                        last_report=time.monotonic();last_count=self.acked
                        self.report("本地菜单已打开，画面暂停，电脑程序继续运行。" if a else "已继续桌面。")
                    elif tag==b"BYE3":self.stop()
                    elif tag==b"MOD3":
                        if hasattr(controller,"set_touch_mode"):controller.set_touch_mode(a)
                    elif tag==b"OVR3":
                        if a:self.overlay.set()
                        else:self.overlay.clear()
                    elif tag==b"KEY3":
                        if self.settings.get("control",True):controller.mouse.shortcut(a)
                    elif tag in (b"ACK1",b"ERR1",b"DRP3"):
                        with self.condition:
                            if a not in self.pending: raise ValueError("接收端返回未知帧号")
                            latency=(time.monotonic()-self.pending.pop(a))*1000
                            if tag==b"ACK1":self.latest_ack_us=min(0xffffffff,round(latency*1000))
                            self.condition.notify_all()
                        if tag==b"DRP3":continue
                        if tag==b"ACK1":
                            self.acked+=1
                            if self.acked==1:self.report(("stage",STREAMING))
                        else:
                            self.failed+=1
                            raise ValueError("接收端拒绝 JPEG 帧：请查看 S3 串口的解码/显示错误")
                        now=time.monotonic()
                        if now-last_report>=1:
                            fps=(self.acked-last_count)/(now-last_report)
                            self.report(f"显示 {fps:.1f} FPS | 解码 {b/1000:.1f} ms | 显示处理 {c/1000:.1f} ms | 帧确认 {latency:.0f} ms | 错误 {self.failed}")
                            last_count=self.acked; last_report=now
                    else: raise ValueError("未知接收端消息")
                if controller and time.monotonic()-last_touch>0.35:
                    controller.release()
                with self.condition:
                    if self.pending and time.monotonic()-min(self.pending.values())>3:
                        raise TimeoutError("3 秒未收到帧确认")
                if time.monotonic()-last_touch>3:
                    raise TimeoutError("接收端心跳超时")
        except Exception as exc:
            if not self.stop_event.is_set(): self.error=exc
            self.stop()
        finally:
            if controller:
                try: controller.release()
                except Exception as exc: self.report(f"释放鼠标失败：{exc}")

    def run(self):
        s=self.settings
        token=token_bytes(s["token"])
        if not 1<=int(s["fps"])<=30 or not 10<=int(s["quality"])<=90:
            raise ValueError("FPS 应为 1–30，JPEG 质量应为 10–90")
        capture=None; scaled=None; receiver=None
        try:
            if self.capture_override:
                monitor, grab = self.capture_override
            else:
                capture=mss.MSS()
                index=int(s["monitor"])
                if not 1<=index<len(capture.monitors): raise ValueError("所选显示器不存在")
                monitor=capture.monitors[index]
            viewport=Viewport.fit(monitor,s.get("toolbar",True))
            if not self.capture_override:
                _, _, width, height = content_geometry(viewport, s["resolution"])
                for backend, label in ((DesktopCapture,"DXGI"),(ScaledCapture,"GDI")):
                    try:
                        scaled=backend(monitor,(width,height))
                        scaled.grab()  # Verify before pairing/streaming.
                        grab=scaled.grab
                        self.report(f"桌面抓屏：{label}")
                        break
                    except (OSError, RuntimeError, ImportError, AttributeError) as exc:
                        if scaled: scaled.close(); scaled=None
                        self.report(f"{label} 抓屏不可用，尝试兼容方式：{exc}")
                if scaled is None:
                    def grab():
                        shot=capture.grab(monitor)
                        return Image.frombytes("RGB",shot.size,shot.bgra,"raw","BGRX")
            controller_type=TouchController if s.get("touch_mode")=="legacy" else SingleTouchController
            args={} if controller_type is TouchController else dict(touch_mode=s.get("touch_mode","direct"))
            controller=controller_type(viewport,self.mouse_override or WindowsMouse(),s.get("toolbar",True),
                                       on_back=self.stop,enabled=s.get("control",True),**args)
            self.socket=socket.create_connection((s["host"],int(s["port"])),timeout=3)
            self.socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            authenticate(self.socket,s.get("host_id",""),s["token"],s.get("device_id",""),s.get("request_id"))
            tag,width,height,limit=MESSAGE.unpack(recv_exact(self.socket,16))
            if (tag,width,height,limit)!=(b"RDY1",800,480,MAX_JPEG):
                raise ValueError("接收端握手或版本不匹配")
            self.socket.settimeout(0.1)
            self.report("已配对，正在传送桌面；停止按钮立即结束控制")
            self.report(("stage",FIRST_FRAME))
            receiver=threading.Thread(target=self._receive,args=(controller,),daemon=True)
            receiver.start()
            interval=1/int(s["fps"]); next_frame=time.monotonic(); sequence=0;last_stats=0;last_overlay=False;last_pause_id=None
            credits=3 if s.get("smooth",False) else 2
            while not self.stop_event.is_set():
                if self.paused.is_set():
                    with self.condition:pause_id=self.pause_id
                    tag=b"PAK3" if pause_id!=last_pause_id else b"NOP3"
                    if not self._send_packet(MESSAGE.pack(tag,pause_id,0,0),"发送菜单暂停确认" if tag==b"PAK3" else "发送菜单心跳"):break
                    last_pause_id=pause_id
                    with self.condition:self.condition.wait_for(lambda:not self.paused.is_set() or self.stop_event.is_set(),timeout=.5)
                    continue
                with self.condition:
                    self.condition.wait_for(lambda:len(self.pending)<credits or self.paused.is_set() or self.stop_event.is_set(),timeout=0.1)
                    if self.stop_event.is_set(): break
                    if self.paused.is_set():continue
                    if len(self.pending)>=credits: continue
                if self.stop_event.wait(max(0,next_frame-time.monotonic())): break
                if self.paused.is_set():continue
                overlay=self.overlay.is_set()
                if overlay!=last_overlay or (overlay and time.monotonic()-last_stats>=1):
                    if not self._send_packet(MESSAGE.pack(b"STA3",self.latest_ack_us,int(overlay),0),"发送统计"):break
                    last_stats=time.monotonic();last_overlay=overlay
                # Capture only after a receive credit is available: no queued old screenshots.
                capture_start=time.perf_counter()
                image=grab()
                encode_start=time.perf_counter()
                jpeg=encode_frame(image,viewport,int(s["quality"]),s["resolution"],s.get("toolbar",True),controller.mode if controller else "VIEW ONLY",None if self.capture_override else cursor_position())
                encode_end=time.perf_counter()
                if self.paused.is_set():continue # Never put a newly captured frame after the pause barrier.
                sequence=(sequence+1)&0xffffffff
                with self.condition: self.pending[sequence]=time.monotonic()
                packet=frame_packet(sequence,jpeg)
                if not self._send_packet(packet,"发送帧"):break
                self.sent+=1
                self.profile["capture_ms"]+=(encode_start-capture_start)*1000
                self.profile["encode_ms"]+=(encode_end-encode_start)*1000
                self.profile["send_ms"]+=(time.perf_counter()-encode_end)*1000
                self.profile["frames"]+=1; self.profile["bytes"]+=len(jpeg)
                next_frame=max(next_frame+interval,time.monotonic())
            if self.error: raise self.error
        finally:
            self.stop()
            if receiver: receiver.join(timeout=4)
            if self.socket: self.socket.close()
            if scaled: scaled.close()
            if capture: capture.close()
