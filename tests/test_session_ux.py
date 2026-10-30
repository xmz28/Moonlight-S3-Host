"""User journeys: one-contact gestures, request lifecycle and stable identity."""
import hashlib
import hmac
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from computer_presence import announcement,parse_status,validate_request,ComputerPresence
from discovery import Device
from input_control import SingleTouchController
from pairing import authenticate
from protocol import Viewport,recv_exact,MESSAGE
from session_control import pack_options,unpack_options
from settings_store import profile_path,save_settings,load_settings
from streamer import StreamSession
from main import App
from unittest.mock import Mock
from test_host import FakeMouse,MONITOR
from test_computer_presence import PC,DEVICE,NONCE,RECORD


def status(flow=1,action=42,nonce=NONCE,options=0x193c011c):
    prefix=f"MS3DEV3 {nonce} {PC} {DEVICE} {action:08x} 1 {options:08x} {flow}".encode()
    return prefix+b" "+hmac.new(RECORD['token'].encode(),prefix,hashlib.sha256).hexdigest().encode()


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.now=1.;self.mouse=FakeMouse()
        self.mouse.relative=lambda dx,dy:self.mouse.events.append(('relative',dx,dy))
        self.touch=SingleTouchController(Viewport.fit(MONITOR),self.mouse,clock=lambda:self.now)

    def test_tap_waits_for_release(self):
        self.touch.update(300,200,1);self.assertIsNone(self.mouse.held)
        self.touch.update(300,200,0)
        self.assertEqual([e for e in self.mouse.events if e[0] in ('down','up')],[('down','LEFT'),('up','LEFT')])

    def test_long_press_right_without_left_click(self):
        self.touch.update(300,200,1);self.now+=.65
        self.touch.update(300,200,1);self.touch.update(300,200,1);self.touch.update(300,200,0)
        self.assertEqual([e for e in self.mouse.events if e[0] in ('down','up')],[('down','RIGHT'),('up','RIGHT')])

    def test_direct_drag_and_release_outside(self):
        self.touch.update(300,200,1);self.touch.update(320,210,1)
        self.assertEqual(self.mouse.held,'LEFT')
        self.touch.update(799,479,1);self.touch.update(799,479,0)
        self.assertIsNone(self.mouse.held);self.assertNotIn(('down','RIGHT'),self.mouse.events)

    def test_trackpad_move_tap_and_double_tap_drag(self):
        self.touch.touch_mode='trackpad'
        self.touch.update(300,200,1);self.touch.update(320,210,1);self.touch.update(320,210,0)
        self.assertIn(('relative',30,15),self.mouse.events);self.assertNotIn(('down','LEFT'),self.mouse.events)
        self.now+=1;self.touch.update(300,200,1);self.touch.update(300,200,0)
        self.now+=.15;self.touch.update(300,200,1);self.assertEqual(self.mouse.held,'LEFT')
        self.touch.update(330,200,1);self.touch.update(330,200,0);self.assertIsNone(self.mouse.held)

    def test_watchdog_requires_actual_lift(self):
        self.touch.update(300,200,1);self.touch.update(320,200,1);self.touch.release()
        self.touch.update(340,200,1);self.assertIsNone(self.mouse.held)
        self.touch.update(340,200,0);self.touch.update(300,200,1);self.touch.update(320,200,1)
        self.assertEqual(self.mouse.held,'LEFT')

    def test_view_only_and_black_bars_do_not_click(self):
        self.touch.enabled=False
        self.touch.update(300,200,1);self.now+=1;self.touch.update(300,200,1);self.touch.update(300,200,0)
        self.assertEqual(self.mouse.events,[])
        self.touch.enabled=True;self.touch.update(0,0,1);self.touch.update(300,200,1);self.touch.update(300,200,0)
        self.assertEqual(self.mouse.events,[])


class LifecycleTests(unittest.TestCase):
    def test_cancel_new_request_while_old_worker_stops(self):
        app=Mock();app.active_request=dict(device_id=DEVICE,action=41)
        app.pending_request=dict(device_id=DEVICE,action=42)
        App.receiver_request(app,dict(device_id=DEVICE,action=42,flow=3))
        self.assertIsNone(app.pending_request);app.stop.assert_not_called()

    def test_signed_options_status_and_busy_announcement(self):
        data=announcement(NONCE,PC,DEVICE,'PC',RECORD,dict(busy=True,phase=6,action=42,monitors=2))
        self.assertIn(b' B 6 0000002a 0 2 ',data)
        parsed=parse_status(status(),NONCE,PC,DEVICE,RECORD)
        self.assertEqual((parsed['version'],parsed['options'],parsed['flow']),(3,0x193c011c,1))
        self.assertIsNone(parse_status(status()[:-1]+b'z',NONCE,PC,DEVICE,RECORD))

    def test_cancelled_or_old_request_cannot_start(self):
        settings=dict(host_id=PC,token=RECORD['token'])
        endpoint=Device(DEVICE,'S3','127.0.0.1',47989)
        for flow,action in ((3,42),(4,42),(1,41),(0,42)):
            with patch('computer_presence.probe_receiver',return_value=dict(paired=True,flow=flow,action=action)):
                with self.assertRaises(ConnectionError):validate_request(settings,endpoint,42)

    def test_cancel_and_expiry_delivered_once_while_announcements_continue(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(.1)
        stop=threading.Event();flow=[1];calls=[];changed=threading.Event();probes=[]
        def serve():
            while not stop.is_set():
                try:data,peer=sock.recvfrom(512)
                except socket.timeout:continue
                probes.append(data);nonce=data.split(b' ')[1].decode();sock.sendto(status(flow=flow[0],nonce=nonce),peer)
        thread=threading.Thread(target=serve);thread.start()
        with patch('computer_presence.PORT',sock.getsockname()[1]),patch('computer_presence.discover',return_value=[Device(DEVICE,'S3','127.0.0.1',47989)]):
            service=ComputerPresence(lambda value:(calls.append(value['flow']),changed.set()),search_interval=.1,poll_interval=.03)
            try:
                service.configure(PC,{DEVICE:RECORD},busy=True,active_device='other',monitors=2)
                self.assertTrue(changed.wait(2));changed.clear();flow[0]=3
                self.assertTrue(changed.wait(2));changed.clear();flow[0]=4
                self.assertTrue(changed.wait(2));self.assertEqual(calls,[1,3,4])
                self.assertTrue(all(b' B ' in data for data in probes))
            finally:service.close();service.thread.join(2)
        stop.set();thread.join(2);sock.close()

    def test_options_roundtrip_preserves_view_only_monitor_and_input(self):
        settings=dict(touch_mode='trackpad',toolbar=False,control=False,resolution='800x480',monitor=2,quality=80,fps=20)
        self.assertEqual(unpack_options(pack_options(settings)),settings)

    def test_au3_contains_exact_request_and_still_validates_proof(self):
        client,server=socket.socketpair();errors=[]
        def serve():
            try:
                with server:
                    server.settimeout(2)
                    self.assertEqual(recv_exact(server,40),b'AU3?'+PC.encode()+b'\x00\x00\x00\x2a')
                    transcript=DEVICE.encode()+PC.encode()+bytes(range(32));server.sendall(b'CHL2'+DEVICE.encode()+bytes(range(32)))
                    self.assertEqual(recv_exact(server,68),b'PRF2'+hmac.new(RECORD['token'].encode(),b'client'+transcript,hashlib.sha256).hexdigest().encode())
                    server.sendall(b'OKA2'+hmac.new(RECORD['token'].encode(),b'server'+transcript,hashlib.sha256).hexdigest().encode())
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=serve);thread.start()
        with client:client.settimeout(2);authenticate(client,PC,RECORD['token'],DEVICE,42)
        thread.join(3)
        if errors:raise errors[0]


class LocalMenuTests(unittest.TestCase):
    def test_fragmented_text_pause_and_view_only(self):
        for enabled in (True,False):
            client,server=socket.socketpair();client.settimeout(.05)
            session=StreamSession(dict(control=enabled));session.socket=client
            mouse=FakeMouse();mouse.text=lambda value:mouse.events.append(('text',value))
            mouse.shortcut=lambda value:mouse.events.append(('key',value))
            controller=SingleTouchController(Viewport.fit(MONITOR),mouse)
            thread=threading.Thread(target=session._receive,args=(controller,));thread.start()
            server.sendall(MESSAGE.pack(b'PAU3',1,0,0)+MESSAGE.pack(b'TXT3',5,0,0)+b'he')
            server.sendall(b'llo'+MESSAGE.pack(b'KEY3',4,0,0)+MESSAGE.pack(b'BYE3',0,0,0))
            thread.join(2);session.stop();client.close();server.close()
            self.assertFalse(thread.is_alive());self.assertIsNone(session.error);self.assertTrue(session.paused.is_set())
            self.assertEqual(mouse.events,[('text','hello'),('key',4)] if enabled else [])


class StableProfileTests(unittest.TestCase):
    def test_upgrade_folder_does_not_replace_identity(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,LOCALAPPDATA=directory):
            old=Path(directory)/'old';new=Path(directory)/'new';old.mkdir();new.mkdir()
            saved=dict(computer_id=PC,pairings={DEVICE:RECORD});save_settings(old/'settings.json',saved)
            first=profile_path(old);save_settings(new/'settings.json',dict(computer_id='f'*32))
            self.assertEqual(profile_path(new),first);self.assertEqual(load_settings(first),saved)
            self.assertEqual(load_settings(old/'settings.json'),saved)
