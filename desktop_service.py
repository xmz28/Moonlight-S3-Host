"""Per-user tray and optional logon startup; no service/session-0 capture."""
import ctypes
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import sys
import threading


def set_startup(enabled,main_file):
    if os.name!="nt":return
    import winreg
    command=[sys.executable,"--background"] if getattr(sys,"frozen",False) else [str(Path(sys.executable).with_name("pythonw.exe")),str(main_file),"--background"]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:winreg.SetValueEx(key,"MoonlightS3Host",0,winreg.REG_SZ,subprocess.list2cmdline(command))
        else:
            try:winreg.DeleteValue(key,"MoonlightS3Host")
            except FileNotFoundError:pass


class DesktopTray:
    def __init__(self,callback,autostart=False):
        self.callback=callback;self.autostart=autostart;self.window=None;self.ready=threading.Event();self.available=False
        if os.name=="nt":threading.Thread(target=self._run,daemon=True).start();self.ready.wait(2)

    def close(self):
        if self.window:self.user.PostMessageW(self.window,0x0010,0,0)

    def _run(self):
        try:self._loop()
        except Exception:self.available=False;self.ready.set()

    def _loop(self):
        user=ctypes.WinDLL("user32",use_last_error=True);shell=ctypes.WinDLL("shell32",use_last_error=True);kernel=ctypes.WinDLL("kernel32",use_last_error=True);self.user=user
        H=W.HANDLE;L=ctypes.c_ssize_t
        PROC=ctypes.WINFUNCTYPE(L,H,W.UINT,W.WPARAM,W.LPARAM)
        class WC(ctypes.Structure):
            _fields_=[("style",W.UINT),("proc",PROC),("extra",ctypes.c_int),("windowExtra",ctypes.c_int),("instance",H),("icon",H),("cursor",H),("brush",H),("menu",W.LPCWSTR),("name",W.LPCWSTR)]
        class NID(ctypes.Structure):
            _fields_=[("size",W.DWORD),("window",H),("id",W.UINT),("flags",W.UINT),("message",W.UINT),("icon",H),("tip",W.WCHAR*128),("state",W.DWORD),("mask",W.DWORD),("info",W.WCHAR*256),("version",W.UINT),("title",W.WCHAR*64),("infoFlags",W.DWORD),("guid",ctypes.c_byte*16),("balloon",H)]
        kernel.GetModuleHandleW.argtypes=[W.LPCWSTR];kernel.GetModuleHandleW.restype=H
        user.DefWindowProcW.argtypes=[H,W.UINT,W.WPARAM,W.LPARAM];user.DefWindowProcW.restype=L
        user.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,H,H,H,ctypes.c_void_p];user.CreateWindowExW.restype=H
        user.RegisterClassW.argtypes=[ctypes.POINTER(WC)];user.RegisterClassW.restype=W.ATOM
        user.LoadIconW.argtypes=[H,ctypes.c_void_p];user.LoadIconW.restype=H
        user.CreatePopupMenu.restype=H;user.AppendMenuW.argtypes=[H,W.UINT,ctypes.c_size_t,W.LPCWSTR]
        user.TrackPopupMenu.argtypes=[H,W.UINT,ctypes.c_int,ctypes.c_int,ctypes.c_int,H,ctypes.c_void_p];user.TrackPopupMenu.restype=W.UINT
        user.SetForegroundWindow.argtypes=[H];user.DestroyMenu.argtypes=[H];user.DestroyWindow.argtypes=[H]
        user.PostMessageW.argtypes=[H,W.UINT,W.WPARAM,W.LPARAM]
        user.GetMessageW.argtypes=[ctypes.POINTER(W.MSG),H,W.UINT,W.UINT];user.GetMessageW.restype=W.BOOL
        user.DispatchMessageW.argtypes=[ctypes.POINTER(W.MSG)];user.DispatchMessageW.restype=L
        shell.Shell_NotifyIconW.argtypes=[W.DWORD,ctypes.POINTER(NID)];shell.Shell_NotifyIconW.restype=W.BOOL
        nid=NID();message=0x8001
        @PROC
        def proc(hwnd,msg,wparam,lparam):
            if msg==message:
                if lparam==0x0203:self.callback("show")
                elif lparam==0x0205:
                    menu=user.CreatePopupMenu();user.AppendMenuW(menu,0,1,"打开设置")
                    user.AppendMenuW(menu,8 if self.autostart else 0,2,"开机后台运行")
                    user.AppendMenuW(menu,0,3,"退出软件")
                    point=W.POINT();user.GetCursorPos(ctypes.byref(point));user.SetForegroundWindow(hwnd)
                    choice=user.TrackPopupMenu(menu,0x0100|0x0002,point.x,point.y,0,hwnd,None);user.DestroyMenu(menu)
                    if choice:self.callback({1:"show",2:"startup",3:"quit"}[choice])
                return 0
            if msg==0x0010:
                shell.Shell_NotifyIconW(2,ctypes.byref(nid));user.DestroyWindow(hwnd);return 0
            if msg==0x0002:user.PostQuitMessage(0);return 0
            return user.DefWindowProcW(hwnd,msg,wparam,lparam)
        self.proc=proc;instance=kernel.GetModuleHandleW(None);wc=WC();wc.proc=proc;wc.instance=instance;wc.name="MoonlightS3HostTray"
        if not user.RegisterClassW(ctypes.byref(wc)):raise ctypes.WinError(ctypes.get_last_error())
        self.window=user.CreateWindowExW(0,wc.name,"Moonlight S3 tray",0,0,0,0,0,None,None,instance,None)
        if not self.window:raise ctypes.WinError(ctypes.get_last_error())
        nid.size=ctypes.sizeof(NID);nid.window=self.window;nid.id=1;nid.flags=7;nid.message=message;nid.icon=user.LoadIconW(None,ctypes.c_void_p(32512));nid.tip="Moonlight S3 · 后台待连接"
        self.available=bool(shell.Shell_NotifyIconW(0,ctypes.byref(nid)));self.ready.set()
        if not self.available:user.DestroyWindow(self.window);return
        event=W.MSG()
        while user.GetMessageW(ctypes.byref(event),None,0,0)>0:user.TranslateMessage(ctypes.byref(event));user.DispatchMessageW(ctypes.byref(event))
        self.window=None;self.available=False
