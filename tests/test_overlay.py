import socket
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from protocol import MESSAGE,MAX_JPEG,Viewport,recv_exact,TOOLBAR_BUTTONS
from input_control import SingleTouchController
from streamer import StreamSession
from test_host import FakeMouse,MONITOR,TOKEN


class OverlayTests(unittest.TestCase):
    def test_menu_neighbor_does_not_disconnect_or_inject_input(self):
        mouse=FakeMouse();back=[]
        touch=SingleTouchController(Viewport.fit(MONITOR),mouse,on_back=lambda:back.append(True))
        touch.update(666,460,1);touch.update(666,460,0)
        self.assertEqual(back,[]);self.assertEqual(mouse.events,[])
        touch.update(665,460,1);touch.update(665,460,0)
        self.assertEqual(back,[True]);self.assertEqual(mouse.events,[])
        widths=[right-left for _,left,right in TOOLBAR_BUTTONS]
        self.assertLessEqual(max(widths)-min(widths),1)

    def test_overlay_metadata_is_serialized_with_frames_and_turns_off(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();errors=[]
        settings=dict(host='127.0.0.1',port=listener.getsockname()[1],token=TOKEN,monitor=1,
                      quality=60,fps=30,resolution='400x240',control=False,toolbar=True,stats=True)
        session=StreamSession(settings,capture=(MONITOR,lambda:Image.new('RGB',(400,225),'blue')),mouse=FakeMouse())
        def server():
            try:
                with listener.accept()[0] as sock:
                    sock.settimeout(3);sock.sendall(MESSAGE.pack(b'RDY1',800,480,MAX_JPEG))
                    self.assertEqual(MESSAGE.unpack(recv_exact(sock,16)),(b'STA3',0,1,0))
                    tag,seq,length,_=MESSAGE.unpack(recv_exact(sock,16));self.assertEqual(tag,b'JPG1');recv_exact(sock,length)
                    session.overlay.clear()
                    sock.sendall(MESSAGE.pack(b'ACK1',seq,12345,45678)+MESSAGE.pack(b'TCH1',0,0,0))
                    for _ in range(6):
                        tag,a,b,c=MESSAGE.unpack(recv_exact(sock,16))
                        if tag==b'STA3':self.assertEqual((b,c),(0,0));break
                        self.assertEqual(tag,b'JPG1');recv_exact(sock,b)
                        sock.sendall(MESSAGE.pack(b'ACK1',a,12345,45678))
                    else:self.fail('Disabling the overlay was not sent')
                    session.stop()
            except BaseException as exc:errors.append(exc);session.stop()
            finally:listener.close()
        thread=threading.Thread(target=server);thread.start()
        with patch('streamer.authenticate'):session.run()
        thread.join(4);self.assertFalse(thread.is_alive())
        if errors:raise errors[0]
