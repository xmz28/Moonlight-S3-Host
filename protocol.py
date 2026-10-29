"""Moonlight S3 protocol v1. All integer fields use network byte order."""
import io
import socket
import struct
import zlib
from dataclasses import dataclass
from PIL import Image, ImageDraw

MESSAGE = struct.Struct("!4sIII")
MAX_JPEG = 256 * 1024
WIDTH, HEIGHT = 800, 480
TOOLBAR_HEIGHT = 32

def token_bytes(token):
    if len(token) != 32 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise ValueError("配对码必须为 32 位十六进制字符")
    return token.encode("ascii")

def recv_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("接收端已断开")
        data.extend(chunk)
    return bytes(data)

def frame_packet(sequence, jpeg):
    if not 4 <= len(jpeg) <= MAX_JPEG:
        raise ValueError("JPEG 大小超出协议限制")
    return MESSAGE.pack(b"JPG1", sequence, len(jpeg), zlib.crc32(jpeg)) + jpeg

@dataclass(frozen=True)
class Viewport:
    left: int
    top: int
    width: int
    height: int
    source: dict

    @classmethod
    def fit(cls, monitor, toolbar=True):
        available = HEIGHT - (TOOLBAR_HEIGHT if toolbar else 0)
        ratio = min(WIDTH / monitor["width"], available / monitor["height"])
        width = max(1, round(monitor["width"] * ratio))
        height = max(1, round(monitor["height"] * ratio))
        return cls((WIDTH-width)//2, (available-height)//2, width, height, monitor)

    def map(self, x, y, clamp=False):
        if not clamp and not (self.left <= x < self.left+self.width and
                              self.top <= y < self.top+self.height):
            return None
        x = min(max(x-self.left, 0), self.width-1)
        y = min(max(y-self.top, 0), self.height-1)
        return (self.source["left"] + round(x*(self.source["width"]-1)/max(1,self.width-1)),
                self.source["top"] + round(y*(self.source["height"]-1)/max(1,self.height-1)))

def encode_frame(image, viewport, quality=60, resolution="400x240", toolbar=True, mode="LEFT", cursor=None):
    canvas = Image.new("RGB", (WIDTH,HEIGHT), (9,13,20))
    canvas.paste(image.resize((viewport.width,viewport.height), Image.Resampling.BILINEAR),
                 (viewport.left,viewport.top))
    if cursor:
        sx,sy=cursor[0]-viewport.source["left"],cursor[1]-viewport.source["top"]
        if 0<=sx<viewport.source["width"] and 0<=sy<viewport.source["height"]:
            x=viewport.left+round(sx*(viewport.width-1)/max(1,viewport.source["width"]-1))
            y=viewport.top+round(sy*(viewport.height-1)/max(1,viewport.source["height"]-1))
            ImageDraw.Draw(canvas).polygon([(x,y),(x,y+18),(x+5,y+13),(x+10,y+21),(x+14,y+19),(x+9,y+11),(x+17,y+11)],fill="white",outline="black")
    if toolbar:
        draw = ImageDraw.Draw(canvas)
        for i, label in enumerate(("LEFT", "RIGHT", "SCROLL", "KEYBOARD")):
            draw.rectangle((i*200,448,(i+1)*200-1,479), fill=(25,85,105) if mode==label else (30,35,45))
            draw.text((i*200+55,457),label,fill="white")
    if resolution == "400x240":
        canvas = canvas.resize((400,240),Image.Resampling.BILINEAR)
    elif resolution != "800x480":
        raise ValueError("不支持的分辨率")
    # Baseline JPEG, 4:2:0: compatible with S3 SIMD decoder.
    for q in range(quality, 9, -10):
        out = io.BytesIO()
        canvas.save(out, "JPEG", quality=q, subsampling=2, progressive=False, optimize=False)
        jpeg = out.getvalue()
        if len(jpeg) <= MAX_JPEG:
            return jpeg
    raise ValueError("压缩帧仍大于 256 KiB，请降低分辨率")
