"""One interactive host per Windows logon session, including other app copies."""
import ctypes
from ctypes import wintypes
import os

TITLE="Moonlight S3 · JPEG 桌面串流"


class SingleInstance:
    def __init__(self,name="Local\\MoonlightS3Host.Interactive"):
        self.handle=None;self.kernel=None;self.name=name

    def acquire(self):
        if os.name!="nt":return True
        self.kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        create=self.kernel.CreateMutexW
        create.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];create.restype=wintypes.HANDLE
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE];self.kernel.CloseHandle.restype=wintypes.BOOL
        ctypes.set_last_error(0)
        handle=create(None,False,self.name)
        error=ctypes.get_last_error()
        if not handle:raise ctypes.WinError(error)
        if error==183:
            self.kernel.CloseHandle(handle);return False
        self.handle=handle;return True

    def activate(self):
        if os.name!="nt":return
        user=ctypes.WinDLL("user32",use_last_error=True)
        user.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];user.FindWindowW.restype=wintypes.HWND
        user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int];user.ShowWindow.restype=wintypes.BOOL
        user.SetForegroundWindow.argtypes=[wintypes.HWND];user.SetForegroundWindow.restype=wintypes.BOOL
        window=user.FindWindowW(None,TITLE)
        if window:user.ShowWindow(window,9);user.SetForegroundWindow(window)

    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
