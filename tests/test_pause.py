import select
import socket
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
from protocol import MESSAGE,MAX_JPEG,recv_exact
from streamer import StreamSession
from test_host import FakeMouse,MONITOR,TOKEN


class SendTests(unittest.TestCase):
    def test_control_and_frame_packets_retry_without_repeating_partial_bytes(self):
        for tag in (b'NOP3',b'PAK3',b'STA3',b'JPG1'):
            with self.subTest(tag=tag):
                packet=MESSAGE.pack(tag,11,22,33)+b'payload'
                sent=bytearray();steps=iter((5,None,3,None,999))
                class Peer:
                    def send(self,data):
                        count=next(steps)
                        if count is None:raise socket.timeout()
                        count=min(count,len(data));sent.extend(data[:count]);return count
                session=StreamSession({});session.socket=Peer()
                self.assertTrue(session._send_packet(packet));self.assertEqual(bytes(sent),packet)

    def test_no_progress_still_times_out_after_three_seconds(self):
        class Peer:
            def send(self,data):raise socket.timeout()
        session=StreamSession({});session.socket=Peer()
        with patch('streamer.time.monotonic',side_effect=(0,3.01)):
            with self.assertRaisesRegex(TimeoutError,'菜单心跳超时'):session._send_packet(b'NOP3','菜单心跳')


class PauseTests(unittest.TestCase):
    def test_drain_barrier_repeated_menus_and_idle_heartbeats(self):
        client,server=socket.socketpair();server.settimeout(3);errors=[];attempts=set()
        class RetrySocket:
            def __getattr__(self,name):return getattr(client,name)
            def send(self,data):
                tag=bytes(data[:4])
                if tag in (b'PAK3',b'NOP3'):
                    if tag not in attempts:
                        attempts.add(tag);time.sleep(.11);raise socket.timeout()
                    return client.send(data[:7])
                return client.send(data)
        session=StreamSession(dict(host='localhost',port=1,token=TOKEN,monitor=1,quality=60,fps=30,
                                   resolution='400x240',control=False,toolbar=True,smooth=True),
                              capture=(MONITOR,lambda:Image.new('RGB',(400,225),'blue')),mouse=FakeMouse())
        def read():
            tag,a,b,c=MESSAGE.unpack(recv_exact(server,16))
            if tag==b'JPG1':recv_exact(server,b)
            return tag,a,b,c
        def receiver():
            try:
                server.sendall(MESSAGE.pack(b'RDY1',800,480,MAX_JPEG))
                for pause_id in range(23,33):
                    # Reach a real frame, then pause with more frames potentially in flight.
                    while True:
                        tag,a,b,c=read()
                        if tag==b'JPG1':break
                        self.assertIn(tag,(b'NOP3',b'STA3'))
                    server.sendall(MESSAGE.pack(b'PAU3',1,pause_id,0)+MESSAGE.pack(b'DRP3',a,0,0)+MESSAGE.pack(b'TCH1',0,0,0))
                    while True:
                        tag,a,b,c=read()
                        if tag==b'PAK3':self.assertEqual(a,pause_id);break
                        if tag==b'JPG1':server.sendall(MESSAGE.pack(b'DRP3',a,0,0))
                        else:self.assertIn(tag,(b'NOP3',b'STA3'))
                    end=time.monotonic()+(3.6 if pause_id==23 else .06)
                    while time.monotonic()<end:
                        server.sendall(MESSAGE.pack(b'TCH1',0,0,0))
                        if select.select([server],[],[],.04)[0]:
                            tag,a,b,c=read();self.assertEqual((tag,a),(b'NOP3',pause_id))
                    self.assertFalse(session.stop_event.is_set(),str(session.error))
                    server.sendall(MESSAGE.pack(b'PAU3',0,pause_id,0)+MESSAGE.pack(b'TCH1',0,0,0))
                session.stop()
            except BaseException as exc:errors.append(exc);session.stop()
            finally:server.close()
        thread=threading.Thread(target=receiver);thread.start()
        with patch('streamer.socket.create_connection',return_value=RetrySocket()),patch('streamer.authenticate'):
            session.run()
        thread.join(5);self.assertFalse(thread.is_alive());self.assertEqual(attempts,{b'PAK3',b'NOP3'})
        if errors:raise errors[0]
