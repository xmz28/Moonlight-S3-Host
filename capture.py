"""Windows capture: scale in GDI before copying pixels into Python."""
import ctypes
from ctypes import wintypes as w
import time
from types import MethodType
from PIL import Image


class DesktopCapture:
    """Pinned DXcam 0.3.0 adapter, with exact monitor-rectangle selection."""
    def __init__(self, monitor, size):
        import dxcam
        self.camera = None
        self.size = size
        # DXcam's public output_info omits desktop origins. Use the pinned
        # factory descriptors to avoid guessing output indices on multiple GPUs.
        factory = getattr(dxcam, "__factory")
        match = None
        wanted = tuple(monitor[k] for k in ("left", "top", "width", "height"))
        for device, outputs in enumerate(factory.outputs):
            for index, output in enumerate(outputs):
                output.update_desc()
                rect = output.desc.DesktopCoordinates
                actual = (rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top)
                if output.attached_to_desktop and actual == wanted:
                    if match is not None: raise OSError("多个桌面输出具有相同边界，请使用兼容抓屏")
                    match = device, index
        if match is None: raise OSError("DXGI 未找到所选显示器")
        self.camera = dxcam.create(device_idx=match[0], output_idx=match[1],
                                   output_color="BGRA", processor_backend="numpy", max_buffer_len=2)
        # 0.3.0 explicitly Releases these owned comtypes pointers and then drops
        # them, causing a second Release in their destructors. Locally let
        # comtypes perform the single Release, including during recovery.
        def release_stage(owner):
            owner.width = owner.height = 0
            owner.interface = None
            owner.texture = None
        def release_duplication(owner):
            owner.release_frame()
            owner.texture = None
            owner.duplicator = None
        self.camera._stagesurf.release = MethodType(release_stage, self.camera._stagesurf)
        self.camera._duplicator.release = MethodType(release_duplication, self.camera._duplicator)
        create_duplication=self.camera._create_duplicator
        def create_owned_duplication():
            owner=create_duplication()
            owner.release=MethodType(release_duplication,owner)
            return owner
        self.camera._create_duplicator=create_owned_duplication

    def grab(self):
        deadline = time.monotonic()+1
        while True:
            frame = self.camera.grab(new_frame_only=False, copy=False)
            if frame is not None: break
            if time.monotonic() >= deadline: raise OSError("DXGI 没有返回桌面图像")
            time.sleep(0.005)
        # Map the BGRA buffer without copying/converting the full desktop.
        # Resize its four byte channels first, then swap R/B on the small image.
        image = Image.frombuffer("RGBX", (frame.shape[1], frame.shape[0]), frame,
                                 "raw", "RGBX", 0, 1)
        image = image.resize(self.size, Image.Resampling.BILINEAR, reducing_gap=2.0)
        blue, green, red, _ = image.split()
        return Image.merge("RGB", (red, green, blue))

    def close(self):
        if self.camera:
            self.camera.release()
            self.camera = None


class BitmapInfo(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                ("image_size", w.DWORD), ("xppm", w.LONG), ("yppm", w.LONG),
                ("used", w.DWORD), ("important", w.DWORD), ("colors", w.DWORD * 3)]


class ScaledCapture:
    def __init__(self, monitor, size):
        self.monitor, self.size = monitor, size
        self.screen = self.dc = self.bitmap = self.previous = None
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.user.GetDC.argtypes = [w.HWND]; self.user.GetDC.restype = w.HDC
        self.user.ReleaseDC.argtypes = [w.HWND, w.HDC]
        signatures = {
            "CreateCompatibleDC": ([w.HDC], w.HDC),
            "CreateDIBSection": ([w.HDC, ctypes.POINTER(BitmapInfo), w.UINT,
                                  ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD], w.HBITMAP),
            "SelectObject": ([w.HDC, w.HANDLE], w.HANDLE),
            "DeleteObject": ([w.HANDLE], w.BOOL), "DeleteDC": ([w.HDC], w.BOOL),
            "SetStretchBltMode": ([w.HDC, ctypes.c_int], ctypes.c_int),
            "SetBrushOrgEx": ([w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p], w.BOOL),
            "StretchBlt": ([w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.DWORD], w.BOOL),
            "GdiFlush": ([], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.gdi, name); function.argtypes = args; function.restype = result
        try:
            self.screen = self.user.GetDC(None)
            if not self.screen: raise ctypes.WinError(ctypes.get_last_error())
            self.dc = self.gdi.CreateCompatibleDC(self.screen)
            if not self.dc: raise ctypes.WinError(ctypes.get_last_error())
            width, height = size
            # Negative height means top-down BGRX, with naturally aligned 32-bit rows.
            info = BitmapInfo(size=40, width=width, height=-height, planes=1, bits=32)
            self.pixels = ctypes.c_void_p()
            self.bitmap = self.gdi.CreateDIBSection(self.screen, ctypes.byref(info), 0,
                                                  ctypes.byref(self.pixels), None, 0)
            if not self.bitmap or not self.pixels.value: raise ctypes.WinError(ctypes.get_last_error())
            self.previous = self.gdi.SelectObject(self.dc, self.bitmap)
            if not self.previous or self.previous == ctypes.c_void_p(-1).value:
                self.previous = None
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.gdi.SetStretchBltMode(self.dc, 4):  # HALFTONE
                raise ctypes.WinError(ctypes.get_last_error())
            self.gdi.SetBrushOrgEx(self.dc, 0, 0, None)
        except BaseException:
            self.close(); raise

    def grab(self):
        m = self.monitor; width, height = self.size
        if not self.gdi.StretchBlt(self.dc, 0, 0, width, height, self.screen,
                                   m["left"], m["top"], m["width"], m["height"], 0x40CC0020):
            raise ctypes.WinError(ctypes.get_last_error())
        # DIB access must follow completion of batched GDI drawing.
        if not self.gdi.GdiFlush(): raise ctypes.WinError(ctypes.get_last_error())
        raw = ctypes.string_at(self.pixels, width * height * 4)
        return Image.frombytes("RGB", self.size, raw, "raw", "BGRX")

    def close(self):
        if self.dc and self.previous:
            self.gdi.SelectObject(self.dc, self.previous); self.previous = None
        if self.bitmap: self.gdi.DeleteObject(self.bitmap); self.bitmap = None
        if self.dc: self.gdi.DeleteDC(self.dc); self.dc = None
        if self.screen: self.user.ReleaseDC(None, self.screen); self.screen = None
