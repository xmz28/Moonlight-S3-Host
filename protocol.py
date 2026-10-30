"""Moonlight S3 protocol v1. All integer fields use network byte order."""
import io
import socket
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from PIL import Image, ImageDraw

MESSAGE = struct.Struct("!4sIII")
MAX_JPEG = 256 * 1024
WIDTH, HEIGHT = 800, 480
TOOLBAR_HEIGHT = 32
TOOLBAR_BUTTONS=tuple((label,i*WIDTH//6,(i+1)*WIDTH//6)
                      for i,label in enumerate(("LEFT","RIGHT","SCROLL","KEYBOARD","BACK","MENU")))

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

def output_size(resolution):
    if resolution == "400x240": return 400,240
    if resolution == "800x480": return WIDTH,HEIGHT
    raise ValueError("不支持的分辨率")


def content_geometry(viewport, resolution):
    width,height=output_size(resolution)
    scale=width/WIDTH
    left,top=round(viewport.left*scale),round(viewport.top*scale)
    return left,top,max(1,round((viewport.left+viewport.width)*scale)-left),max(1,round((viewport.top+viewport.height)*scale)-top)


@lru_cache(maxsize=16)
def toolbar_image(resolution, mode):
    bar=Image.new("RGB",(WIDTH,TOOLBAR_HEIGHT))
    draw=ImageDraw.Draw(bar)
    for label,left,right in TOOLBAR_BUTTONS:
        draw.rectangle((left,0,right-1,31),fill=(25,85,105) if mode==label else (30,35,45))
        box=draw.textbbox((0,0),label)
        draw.text((left+(right-left-(box[2]-box[0]))//2,9),label,fill="white")
    if resolution=="400x240": bar=bar.resize((400,16),Image.Resampling.BILINEAR)
    return bar


def encode_frame(image, viewport, quality=60, resolution="400x240", toolbar=True, mode="LEFT", cursor=None):
    size=output_size(resolution)
    scale=size[0]/WIDTH
    left,top,width,height=content_geometry(viewport,resolution)
    canvas = Image.new("RGB",size,(9,13,20))
    # A GDI capture is already at this size; compatibility capture needs one resize.
    if image.size!=(width,height):
        image=image.resize((width,height),Image.Resampling.BILINEAR,reducing_gap=2.0)
    canvas.paste(image,(left,top))
    if cursor:
        sx,sy=cursor[0]-viewport.source["left"],cursor[1]-viewport.source["top"]
        if 0<=sx<viewport.source["width"] and 0<=sy<viewport.source["height"]:
            x=viewport.left+sx*(viewport.width-1)/max(1,viewport.source["width"]-1)
            y=viewport.top+sy*(viewport.height-1)/max(1,viewport.source["height"]-1)
            points=[(round((x+dx)*scale),round((y+dy)*scale)) for dx,dy in ((0,0),(0,18),(5,13),(10,21),(14,19),(9,11),(17,11))]
            ImageDraw.Draw(canvas).polygon(points,fill="white",outline="black")
    if toolbar:
        canvas.paste(toolbar_image(resolution,mode),(0,round(448*scale)))
    else:
        # Keep the local escape available at the same position when the bar is hidden.
        canvas.paste(toolbar_image(resolution,mode).crop((round(666*scale),0,size[0],round(32*scale))),
                     (round(666*scale),round(448*scale)))
    # Baseline JPEG, 4:2:0: compatible with S3 SIMD decoder.
    for q in range(quality, 9, -10):
        out = io.BytesIO()
        canvas.save(out, "JPEG", quality=q, subsampling=2, progressive=False, optimize=False)
        jpeg = out.getvalue()
        if len(jpeg) <= MAX_JPEG:
            return jpeg
    raise ValueError("压缩帧仍大于 256 KiB，请降低分辨率")
