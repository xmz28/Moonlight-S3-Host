import socket
import threading
import time
from PIL import Image
import mss
from protocol import MESSAGE, MAX_JPEG, Viewport, encode_frame, frame_packet, recv_exact, token_bytes
from input_control import WindowsMouse, TouchController, cursor_position

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

    def stop(self):
        self.stop_event.set()
        with self.condition: self.condition.notify_all()
        if self.socket:
            try: self.socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass

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
                    tag,a,b,c = MESSAGE.unpack(buffer[:16]); del buffer[:16]
                    if tag==b"TCH1":
                        if controller: controller.update(a,b,c)
                        last_touch=time.monotonic()
                    elif tag in (b"ACK1",b"ERR1"):
                        with self.condition:
                            if a not in self.pending: raise ValueError("接收端返回未知帧号")
                            latency=(time.monotonic()-self.pending.pop(a))*1000
                            self.condition.notify_all()
                        if tag==b"ACK1": self.acked+=1
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
        capture=None; receiver=None
        try:
            if self.capture_override:
                monitor, grab = self.capture_override
            else:
                capture=mss.MSS()
                index=int(s["monitor"])
                if not 1<=index<len(capture.monitors): raise ValueError("所选显示器不存在")
                monitor=capture.monitors[index]
                def grab():
                    shot=capture.grab(monitor)
                    return Image.frombytes("RGB",shot.size,shot.rgb)
            viewport=Viewport.fit(monitor,s.get("toolbar",True))
            controller=TouchController(viewport,self.mouse_override or WindowsMouse(),s.get("toolbar",True)) if s.get("control",True) else None
            self.socket=socket.create_connection((s["host"],int(s["port"])),timeout=3)
            self.socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            self.socket.sendall(b"AUT1"+token)
            tag,width,height,limit=MESSAGE.unpack(recv_exact(self.socket,16))
            if (tag,width,height,limit)!=(b"RDY1",800,480,MAX_JPEG):
                raise ValueError("接收端握手或版本不匹配")
            self.socket.settimeout(0.1)
            self.report("已配对，正在传送桌面；停止按钮立即结束控制")
            receiver=threading.Thread(target=self._receive,args=(controller,),daemon=True)
            receiver.start()
            interval=1/int(s["fps"]); next_frame=time.monotonic(); sequence=0
            while not self.stop_event.is_set():
                with self.condition:
                    self.condition.wait_for(lambda:len(self.pending)<2 or self.stop_event.is_set(),timeout=0.1)
                    if self.stop_event.is_set(): break
                    if len(self.pending)>=2: continue
                if self.stop_event.wait(max(0,next_frame-time.monotonic())): break
                # Capture only after a receive credit is available: no queued old screenshots.
                jpeg=encode_frame(grab(),viewport,int(s["quality"]),s["resolution"],s.get("toolbar",True),controller.mode if controller else "VIEW ONLY",None if self.capture_override else cursor_position())
                sequence=(sequence+1)&0xffffffff
                with self.condition: self.pending[sequence]=time.monotonic()
                # A short per-recv timeout must not make slow Wi-Fi writes fail after 100 ms.
                packet=frame_packet(sequence,jpeg)
                view=memoryview(packet); deadline=time.monotonic()+3
                while view and not self.stop_event.is_set():
                    try:
                        count=self.socket.send(view)
                        if not count: raise ConnectionError("发送连接断开")
                        view=view[count:]
                    except socket.timeout:
                        if time.monotonic()>deadline: raise TimeoutError("发送帧超时")
                self.sent+=1
                next_frame=max(next_frame+interval,time.monotonic())
            if self.error: raise self.error
        finally:
            self.stop()
            if receiver: receiver.join(timeout=4)
            if self.socket: self.socket.close()
            if capture: capture.close()
