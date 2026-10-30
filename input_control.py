"""Coordinate mapping and Win32 input. No input is sent until a paired session runs."""
import ctypes
from ctypes import wintypes
import os
import subprocess
import time
import math
from protocol import TOOLBAR_BUTTONS

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",wintypes.LONG),("dy",wintypes.LONG),("mouseData",wintypes.DWORD),
                ("dwFlags",wintypes.DWORD),("time",wintypes.DWORD),("dwExtraInfo",ctypes.c_size_t)]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",wintypes.WORD),("wScan",wintypes.WORD),("dwFlags",wintypes.DWORD),
                ("time",wintypes.DWORD),("dwExtraInfo",ctypes.c_size_t)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg",wintypes.DWORD),("wParamL",wintypes.WORD),("wParamH",wintypes.WORD)]
class INPUTUNION(ctypes.Union):
    _fields_ = [("mi",MOUSEINPUT),("ki",KEYBDINPUT),("hi",HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type",wintypes.DWORD),("u",INPUTUNION)]

def dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()

def cursor_position():
    point = wintypes.POINT()
    return (point.x,point.y) if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)) else None

class WindowsMouse:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [wintypes.UINT,ctypes.POINTER(INPUT),ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.held = None

    def _send(self, flags, x=0, y=0, data=0):
        event = INPUT(type=0, mi=MOUSEINPUT(x,y,data & 0xffffffff,flags,0,0))
        if self.user32.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT)) != 1:
            raise OSError("Windows 拒绝输入注入（目标窗口可能以管理员权限运行）")

    def move(self,x,y):
        left,top,width,height = (self.user32.GetSystemMetrics(i) for i in (76,77,78,79))
        nx = min(65535,max(0,round((x-left)*65535/max(1,width-1))))
        ny = min(65535,max(0,round((y-top)*65535/max(1,height-1))))
        self._send(0x8000|0x4000|0x0001,nx,ny)

    def down(self,button):
        if self.held == button: return
        self.release()
        self._send(0x0002 if button=="LEFT" else 0x0008)
        self.held = button

    def release(self):
        if self.held:
            button = self.held
            self._send(0x0004 if button=="LEFT" else 0x0010)
            self.held = None

    def wheel(self,steps):
        self._send(0x0800,data=steps*120)

    def keyboard(self):
        subprocess.Popen([os.path.join(os.environ.get("WINDIR",r"C:\Windows"),"System32","osk.exe")])

    def relative(self,dx,dy):self._send(0x0001,int(dx),int(dy))

    def _key(self,vk=0,scan=0,flags=0):
        event=INPUT(type=1,ki=KEYBDINPUT(vk,scan,flags,0,0))
        if self.user32.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:raise OSError("Windows 拒绝键盘输入注入")

    def shortcut(self,index):
        keys=((0x1b,),(0x0d,),(0x09,),(0x08,),(0x11,0x43),(0x11,0x56),(0x11,0x41),(0x12,0x09))
        if not 0<=index<len(keys):raise ValueError("未知快捷键")
        held=[]
        try:
            for vk in keys[index]:self._key(vk);held.append(vk)
        finally:
            for vk in reversed(held):self._key(vk,flags=2)

    def text(self,value):
        encoded=value.encode("utf-16-le")
        for offset in range(0,len(encoded),2):
            unit=int.from_bytes(encoded[offset:offset+2],"little")
            self._key(scan=unit,flags=4);self._key(scan=unit,flags=6)

class TouchController:
    def __init__(self, viewport, mouse, toolbar=True, on_back=None, enabled=True):
        self.viewport, self.mouse, self.toolbar = viewport, mouse, toolbar
        self.on_back,self.enabled=on_back,enabled
        self.mode = "LEFT" if enabled else "VIEW ONLY"
        self.active = self.blocked = self.previous = False
        self.scroll_y = 0

    def release(self):
        self.mouse.release()
        self.active = False
        # A timeout must require an actual touch-up before a new press.
        self.blocked = True

    def update(self,x,y,down):
        if not (0<=x<800 and 0<=y<480 and down in (0,1)):
            raise ValueError("无效触摸事件")
        if not down:
            self.mouse.release()
            self.active = self.blocked = self.previous = False
            return
        first = not self.previous
        self.previous = True
        if self.blocked: return
        if first and self.toolbar and y>=448:
            self.mouse.release()
            label = next(label for label,left,right in TOOLBAR_BUTTONS if left<=x<right)
            if label=="BACK":
                if self.on_back:self.on_back()
            elif label=="MENU" or not self.enabled:pass  # S3 handles MENU locally.
            elif label == "KEYBOARD":
                self.mouse.keyboard()
                self.mode = "LEFT"
            else: self.mode = label
            self.blocked = True
            return
        if not self.enabled:return
        mapped = self.viewport.map(x,y,clamp=self.active)
        if mapped is None:
            self.blocked = True
            return
        if self.mode == "SCROLL":
            if not self.active:
                self.mouse.move(*mapped)
                self.scroll_y = y
            steps = int((y-self.scroll_y)/18)
            if steps:
                self.mouse.wheel(steps)
                self.scroll_y += steps*18
        else:
            self.mouse.move(*mapped)
            self.mouse.down(self.mode)
        self.active = True


class SingleTouchController(TouchController):
    """One contact only: tap, long-press right click, drag, relative trackpad."""
    def __init__(self,*args,touch_mode="direct",clock=time.monotonic,**kwargs):
        super().__init__(*args,**kwargs)
        self.touch_mode=touch_mode;self.clock=clock;self.started=0;self.origin=(0,0);self.last=(0,0)
        self.moved=False;self.right_clicked=False;self.dragging=False;self.last_tap=-10

    def set_touch_mode(self,mode):
        self.release();self.touch_mode="trackpad" if mode else "direct"

    def release(self):
        super().release();self.dragging=False;self.right_clicked=True

    def update(self,x,y,down):
        if not(0<=x<800 and 0<=y<480 and down in (0,1)):raise ValueError("无效触摸事件")
        now=self.clock()
        if not down:
            if self.previous and not self.blocked and self.enabled and self.mode=="LEFT" and not self.dragging and not self.right_clicked and not self.moved:
                self.mouse.down("LEFT");self.mouse.release();self.last_tap=now
            self.mouse.release();self.active=self.blocked=self.previous=False;self.dragging=False;return
        first=not self.previous
        # Manual RIGHT/SCROLL and the existing toolbar remain one-contact operations.
        if (first and self.toolbar and y>=448) or self.mode!="LEFT":
            return super().update(x,y,down)
        self.previous=True
        if self.blocked or not self.enabled:return
        mapped=self.viewport.map(x,y,clamp=self.active)
        if mapped is None:self.blocked=True;return
        if first:
            self.started=now;self.origin=self.last=(x,y);self.moved=self.right_clicked=self.dragging=False
            if self.touch_mode=="direct":self.mouse.move(*mapped)
            elif now-self.last_tap<.3:self.mouse.down("LEFT");self.dragging=True
            self.active=True;return
        distance=math.hypot(x-self.origin[0],y-self.origin[1])
        if distance>=8:self.moved=True
        if self.touch_mode=="trackpad":
            dx,dy=x-self.last[0],y-self.last[1]
            if dx or dy:self.mouse.relative(round(dx*1.5),round(dy*1.5))
        elif self.moved:
            if not self.dragging and not self.right_clicked:self.mouse.down("LEFT");self.dragging=True
            self.mouse.move(*mapped)
        self.last=(x,y)
        if not self.moved and not self.dragging and not self.right_clicked and now-self.started>=.6:
            self.mouse.down("RIGHT");self.mouse.release();self.right_clicked=True
