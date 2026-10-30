import hashlib
import hmac
import unittest
from remote_start import query_packet,parse_response

TOKEN="0123456789abcdef0123456789abcdef"
NONCE="1234567890abcdef1234567890abcdef"
IDENTITY="b81f3fc4c470"


class RemoteStartTests(unittest.TestCase):
    def test_request_has_signature_and_never_contains_pairing_token(self):
        packet=query_packet(TOKEN,NONCE)
        self.assertEqual(len(packet),105)
        prefix,signature=packet.rsplit(b" ",1)
        self.assertEqual(signature,hmac.new(TOKEN.encode(),prefix,hashlib.sha256).hexdigest().encode())
        self.assertNotIn(TOKEN.encode(),packet)

    def test_reply_requires_nonce_signature_and_exact_identity(self):
        prefix=f"MS3CTL1 {NONCE} {IDENTITY} 1234abcd".encode()
        packet=prefix+b" "+hmac.new(TOKEN.encode(),prefix,hashlib.sha256).hexdigest().encode()
        self.assertEqual(parse_response(packet,TOKEN,NONCE,IDENTITY),(IDENTITY,0x1234abcd))
        self.assertIsNone(parse_response(packet,TOKEN,"0"*32,IDENTITY))
        self.assertIsNone(parse_response(packet,TOKEN,NONCE,"001122334455"))
        self.assertIsNone(parse_response(packet,"0"*32,NONCE,IDENTITY))
        self.assertIsNone(parse_response(packet[:-1]+b"!",TOKEN,NONCE,IDENTITY))
        for bad in (b"bad",b"\xff",packet+b" extra"):
            self.assertIsNone(parse_response(bad,TOKEN,NONCE,IDENTITY))
