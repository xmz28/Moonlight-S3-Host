import socket
import threading
import unittest
from discovery import discover,parse_reply
from wifi_setup import credentials_command,provision

NONCE="0123456789abcdef0123456789abcdef"

class DiscoveryTests(unittest.TestCase):
    def test_reply_validation(self):
        valid=f"MS3HERE1 {NONCE} 123456abcdef 47989 moonlight-s3-abcdef".encode()
        device=parse_reply(valid,("192.168.8.6",47990),NONCE)
        self.assertEqual(device.identity,"123456abcdef")
        self.assertEqual(device.host,"192.168.8.6")
        for bad in (valid.replace(NONCE.encode(),b"0"*32), valid.replace(b"47989",b"70000"),
                    valid.replace(b"moonlight-s3-abcdef",b"other-device"),valid+b" extra",b"\xff",b"a"*193):
            self.assertIsNone(parse_reply(bad,("192.168.8.6",47990),NONCE))
        self.assertIsNone(parse_reply(valid,("224.0.0.1",47990),NONCE))

    def test_loopback_discovery_deduplicates_without_name_guessing(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1",0)); sock.settimeout(2)
        endpoint=sock.getsockname(); errors=[]
        def serve():
            try:
                data,peer=sock.recvfrom(256)
                self.assertTrue(data.startswith(b"MS3DISC1 "))
                nonce=data.split()[1]
                for identity in (b"123456abcdef",b"123456abcdef",b"000001abcdef"):
                    sock.sendto(b"MS3HERE1 "+nonce+b" "+identity+b" 47989 moonlight-s3-abcdef",peer)
                sock.sendto(b"MS3HERE1 "+b"0"*32+b" 999999abcdef 47989 moonlight-s3-abcdef",peer)
            except BaseException as exc: errors.append(exc)
            finally: sock.close()
        worker=threading.Thread(target=serve); worker.start()
        devices=discover(timeout=0.3,targets=[endpoint],bind_addresses=["127.0.0.1"])
        worker.join(3)
        if errors: raise errors[0]
        self.assertEqual({d.identity for d in devices},{"123456abcdef","000001abcdef"})
        self.assertEqual(len(devices),2)

class FakeSerial:
    def __init__(self,**kwargs):
        self.writes=[]; self.pending=[]; self.closed=False
        self.port=kwargs["port"]
    def __enter__(self): return self
    def __exit__(self,*args): self.closed=True
    def open(self):
        assert self.dtr is False and self.rts is False
        assert self.port=="COM_TEST"
    def write(self,data):
        self.writes.append(data)
        if data==b"MS3STATUS1\n":
            self.pending.extend([b"boot log\n",b"MS3STATUS1 123456abcdef 0.0.0.0 UNCONFIGURED\n"])
        else: self.pending.append(b"MS3WIFI1 OK RESTART\n")
    def readline(self,size): return self.pending.pop(0) if self.pending else b""
    def flush(self): pass

class ProvisionTests(unittest.TestCase):
    def test_utf8_spaces_and_open_network(self):
        command=credentials_command("客厅 WiFi","password 123")
        _,ssid,password=command.strip().split(b" ")
        self.assertEqual(bytes.fromhex(ssid.decode()).decode(),"客厅 WiFi")
        self.assertEqual(bytes.fromhex(password.decode()).decode(),"password 123")
        self.assertTrue(credentials_command("Open","").endswith(b" -\n"))
        credentials_command("WPA2","a"*64)

    def test_reject_invalid_lengths_and_nulls(self):
        for ssid,password in (("","password"),("a"*33,"password"),("a\0","password"),
                              ("test","short"),("test","g"*64),("test","a"*65),("test","abc\0defgh")):
            with self.assertRaises(ValueError): credentials_command(ssid,password)

    def test_identify_before_writing_and_close_after_ack(self):
        devices=[]
        def factory(**kwargs):
            device=FakeSerial(**kwargs); devices.append(device); return device
        provision("COM_TEST","Home WiFi","password123",serial_factory=factory)
        self.assertEqual(devices[0].writes,[b"MS3STATUS1\n",credentials_command("Home WiFi","password123")])
        self.assertTrue(devices[0].closed)

    def test_wrong_device_does_not_receive_credentials(self):
        devices=[]
        class WrongDevice(FakeSerial):
            def readline(self,size): raise OSError("unrecognized device")
        def factory(**kwargs):
            device=WrongDevice(**kwargs); devices.append(device); return device
        with self.assertRaises(OSError): provision("COM_TEST","Home","password123",serial_factory=factory)
        self.assertEqual(devices[0].writes,[b"MS3STATUS1\n"])
        self.assertTrue(devices[0].closed)
