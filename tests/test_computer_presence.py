import hashlib
import hmac
import socket
import threading
import unittest
from unittest.mock import patch
from computer_presence import announcement,parse_status,computer_identity,ComputerPresence,name_hex
from discovery import Device

PC="a"*32
DEVICE="b"*12
NONCE="c"*32
RECORD=dict(host_id=PC,token="0123456789abcdef"*2)


def reply(nonce=NONCE,computer=PC,device=DEVICE,paired=True,action="00000042"):
    prefix=f"MS3DEV2 {nonce} {computer} {device} {action} {int(paired)}".encode()
    signature=hmac.new(RECORD["token"].encode(),prefix,hashlib.sha256).hexdigest().encode() if paired else b"-"
    return prefix+b" "+signature


class PresenceTests(unittest.TestCase):
    def test_announcement_hides_key_and_checks_host_binding(self):
        data=announcement(NONCE,PC,DEVICE,"我的电脑",RECORD)
        prefix,signature=data.rsplit(b" ",1)
        self.assertEqual(signature,hmac.new(RECORD["token"].encode(),prefix,hashlib.sha256).hexdigest().encode())
        self.assertNotIn(RECORD["token"].encode(),data)
        self.assertIn("我的电脑".encode().hex().encode(),data)
        self.assertTrue(announcement(NONCE,"e"*32,DEVICE,"PC",RECORD).endswith(b" -"))

    def test_only_signed_known_status_can_start_without_pin(self):
        result=parse_status(reply(),NONCE,PC,DEVICE,RECORD)
        self.assertTrue(result["paired"]);self.assertEqual(result["action"],66)
        self.assertIsNone(parse_status(reply(),NONCE,PC,DEVICE,{}))
        self.assertIsNone(parse_status(reply(nonce="f"*32),NONCE,PC,DEVICE,RECORD))
        self.assertIsNone(parse_status(reply(device="0"*12),NONCE,PC,DEVICE,RECORD))
        self.assertIsNone(parse_status(reply()[:-1]+b"0",NONCE,PC,DEVICE,RECORD))
        result=parse_status(reply(paired=False),NONCE,PC,DEVICE,{})
        self.assertFalse(result["paired"])

    def test_identity_migrates_and_names_are_utf8_bounded(self):
        self.assertEqual(computer_identity(dict(pairings={DEVICE:RECORD})),PC)
        self.assertEqual(computer_identity(dict(computer_id=PC)),PC)
        name=bytes.fromhex(name_hex("中"*100+"\n"))
        self.assertLessEqual(len(name),48);self.assertTrue(name.decode())

    def test_outbound_udp_roundtrip_and_request_deduplication(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        listener.bind(("127.0.0.1",0));listener.settimeout(.3)
        port=listener.getsockname()[1];stop=threading.Event();received=threading.Event();calls=[]
        def server():
            while not stop.is_set():
                try:data,peer=listener.recvfrom(512)
                except socket.timeout:continue
                nonce=data.split(b" ")[1].decode()
                listener.sendto(reply(nonce=nonce),peer)
        thread=threading.Thread(target=server);thread.start()
        with patch("computer_presence.PORT",port),patch("computer_presence.discover",return_value=[Device(DEVICE,"moonlight-s3-"+DEVICE[-6:],"127.0.0.1",47989)]):
            service=ComputerPresence(lambda result:(calls.append(result),received.set()))
            try:
                service.configure(PC,{DEVICE:RECORD})
                self.assertTrue(received.wait(3))
                # Same physical request ID must not create repeated PIN dialogs/starts.
                received.clear();self.assertFalse(received.wait(1.5));self.assertEqual(len(calls),1)
            finally:service.close();service.thread.join(3)
        stop.set();thread.join(2);listener.close()
        self.assertEqual(calls[0]["host"],"127.0.0.1")
        self.assertTrue(calls[0]["paired"])


if __name__=="__main__":unittest.main()
