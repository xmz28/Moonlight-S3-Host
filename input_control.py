"""Coordinate mapping and Win32 input. No input is sent until a paired session runs."""
import ctypes
from ctypes import wintypes
import os
import subprocess

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

class TouchController:
    def __init__(self, viewport, mouse, toolbar=True):
        self.viewport, self.mouse, self.toolbar = viewport, mouse, toolbar
        self.mode = "LEFT"
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
            label = ("LEFT","RIGHT","SCROLL","KEYBOARD")[x//200]
            if label == "KEYBOARD":
                self.mouse.keyboard()
                self.mode = "LEFT"
            else: self.mode = label
            self.blocked = True
            return
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
