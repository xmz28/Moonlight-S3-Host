import io
from pathlib import Path
import socket
import struct
import threading
import time
import unittest
import zlib
from PIL import Image
from protocol import MESSAGE, MAX_JPEG, Viewport, encode_frame, frame_packet, recv_exact, token_bytes
from input_control import TouchController, INPUT
from streamer import StreamSession
import ctypes

MONITOR=dict(left=-1920,top=100,width=1920,height=1080)
TOKEN="0123456789abcdef0123456789abcdef"

class FakeMouse:
    def __init__(self):
        self.events=[]; self.held=None; self.pressed=threading.Event()
    def move(self,*xy): self.events.append(("move",*xy))
    def down(self,button):
        self.held=button; self.events.append(("down",button)); self.pressed.set()
    def release(self):
        if self.held: self.events.append(("up",self.held))
        self.held=None
    def wheel(self,steps): self.events.append(("wheel",steps))
    def keyboard(self): self.events.append(("keyboard",))

class ProtocolTests(unittest.TestCase):
    def test_crc_and_wire_layout(self):
        packet=frame_packet(0x12345678,b"123456789")
        self.assertEqual(packet[:16].hex(),"4a5047311234567800000009cbf43926")
        self.assertEqual(len(packet),25)
        for data in (b"",b"a"*(MAX_JPEG+1)):
            with self.assertRaises(ValueError): frame_packet(1,data)

    def test_auth_validation(self):
        self.assertEqual(len(token_bytes(TOKEN)),32)
        for token in ("", "g"*32,"0"*31):
            with self.assertRaises(ValueError): token_bytes(token)

    def test_letterbox_mapping_negative_monitor_and_edges(self):
        v=Viewport.fit(MONITOR,True)
        self.assertIsNone(v.map(0,0))
        self.assertEqual(v.map(v.left,v.top),(-1920,100))
        self.assertEqual(v.map(v.left+v.width-1,v.top+v.height-1),(-1,1179))
        self.assertEqual(v.map(900,900,True),(-1,1179))

    def test_baseline_420_and_both_resolutions(self):
        v=Viewport.fit(MONITOR)
        for resolution in ("400x240","800x480"):
            jpeg=encode_frame(Image.new("RGB",(1920,1080),"blue"),v,resolution=resolution)
            image=Image.open(io.BytesIO(jpeg)); image.load()
            self.assertEqual(image.size,tuple(map(int,resolution.split("x"))))
            self.assertNotIn("progression",image.info)
            self.assertEqual(image.layer[0][1:3],(2,2))
            self.assertLess(len(jpeg),MAX_JPEG)

    def test_windows_input_abi(self):
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

class TouchTests(unittest.TestCase):
    def setUp(self):
        self.mouse=FakeMouse(); self.touch=TouchController(Viewport.fit(MONITOR),self.mouse)
    def test_drag_outside_then_release(self):
        self.touch.update(300,200,1)
        self.touch.update(799,479,1)
        self.assertEqual(self.mouse.held,"LEFT")
        self.touch.update(799,479,0)
        self.assertIsNone(self.mouse.held)
    def test_black_bar_does_not_press(self):
        self.touch.update(0,0,1)
        self.touch.update(300,200,1)
        self.assertFalse(self.mouse.events)
    def test_toolbar_right_scroll_keyboard(self):
        for x,mode in ((250,"RIGHT"),(450,"SCROLL")):
            self.touch.update(x,460,1); self.touch.update(x,460,0)
            self.assertEqual(self.touch.mode,mode)
        self.touch.update(300,200,1); self.touch.update(300,240,1)
        self.assertIn(("wheel",2),self.mouse.events)
        self.touch.update(300,240,0)
        self.touch.update(650,460,1)
        self.assertIn(("keyboard",),self.mouse.events)
        self.assertEqual(self.touch.mode,"LEFT")
    def test_timeout_requires_lift(self):
        self.touch.update(300,200,1); self.touch.release()
        self.touch.update(300,200,1)
        self.assertIsNone(self.mouse.held)
        self.touch.update(300,200,0); self.touch.update(300,200,1)
        self.assertEqual(self.mouse.held,"LEFT")
    def test_invalid_coordinates(self):
        with self.assertRaises(ValueError): self.touch.update(800,0,1)

class NetworkTests(unittest.TestCase):
    def exercise(self, disconnect=False, smooth=False):
        window=3 if smooth else 2
        listener=socket.socket(); listener.bind(("127.0.0.1",0)); listener.listen()
        port=listener.getsockname()[1]
        errors=[]; frames=[]; mouse=FakeMouse()
        settings=dict(host="127.0.0.1",port=port,token=TOKEN,monitor=1,quality=60,fps=30,
                      resolution="400x240",control=True,toolbar=True,smooth=smooth)
        session=StreamSession(settings,capture=(MONITOR,lambda:Image.new("RGB",(1920,1080),"green")),mouse=mouse)
        def emulator():
            try:
                with listener.accept()[0] as conn:
                    conn.settimeout(2)
                    self.assertEqual(recv_exact(conn,36),b"AUT1"+TOKEN.encode())
                    hello=MESSAGE.pack(b"RDY1",800,480,MAX_JPEG)
                    conn.sendall(hello[:3]); conn.sendall(hello[3:])
                    for _ in range(window):
                        tag,seq,length,crc=MESSAGE.unpack(recv_exact(conn,16))
                        data=recv_exact(conn,length)
                        self.assertEqual(tag,b"JPG1"); self.assertEqual(zlib.crc32(data),crc)
                        self.assertEqual(Image.open(io.BytesIO(data)).size,(400,240))
                        frames.append(seq)
                    # Neither mode may send past its credit limit before an ACK.
                    conn.settimeout(0.15)
                    with self.assertRaises(socket.timeout): conn.recv(1)
                    # Real S3 sends touch-up heartbeats while idle. Recover from any
                    # watchdog timeout during slow frame encoding before pressing.
                    conn.sendall(MESSAGE.pack(b"TCH1",300,200,0))
                    touch=MESSAGE.pack(b"TCH1",300,200,1)
                    conn.sendall(touch[:5]); time.sleep(0.02); conn.sendall(touch[5:])
                    self.assertTrue(mouse.pressed.wait(1),"Touch-down was not processed")
                    if disconnect: return
                    # No touch updates: receiver watchdog must release held mouse.
                    time.sleep(0.45)
                    self.assertIsNone(mouse.held)
                    conn.sendall(MESSAGE.pack(b"TCH1",300,200,0)+MESSAGE.pack(b"ACK1",frames[0],12000,40000))
                    conn.settimeout(2)
                    _,seq,length,crc=MESSAGE.unpack(recv_exact(conn,16))
                    self.assertEqual(zlib.crc32(recv_exact(conn,length)),crc)
                    frames.append(seq)
                    session.stop()
            except BaseException as exc: errors.append(exc); session.stop()
            finally: listener.close()
        server=threading.Thread(target=emulator); server.start()
        try:
            try: session.run()
            except ConnectionError:
                if not disconnect: raise
        finally:
            session.stop(); server.join(timeout=4)
        self.assertFalse(server.is_alive())
        if errors: raise errors[0]
        self.assertIsNone(mouse.held)
        self.assertIn(("up","LEFT"),mouse.events)
        self.assertEqual(len(frames),window if disconnect else window+1)
    def test_fragmentation_flow_control_and_watchdog(self): self.exercise()
    def test_disconnect_releases_mouse(self): self.exercise(True)
    def test_smooth_flow_control_and_watchdog(self): self.exercise(smooth=True)
    def test_smooth_disconnect_releases_mouse(self): self.exercise(True,smooth=True)

if __name__=="__main__": unittest.main()
