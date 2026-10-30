import hashlib
import hmac
import socket
import threading
import unittest

from pairing import N, G, padded, client_exchange, authenticate, pair
from protocol import recv_exact


DEVICE="b81f3fc4c470"
HOST="0123456789abcdef"*2
TOKEN="fedcba9876543210"*2


class PairingTests(unittest.TestCase):
    def server_exchange(self, pin="0042", client_pin="0042", device=DEVICE, host=HOST):
        # Independent server equations, fixed non-secret values for reproducible tests.
        H=lambda data:hashlib.sha256(data).digest()
        salt=bytes(range(16));b=int.from_bytes(bytes(range(32)),"big")
        x=int.from_bytes(H(salt+H(f"MoonlightS3:{device}:{pin}".encode())),"big")
        v=pow(G,x,N);k=int.from_bytes(H(padded(N)+padded(G)),"big")
        B=(k*v+pow(G,b,N))%N
        challenge=b"SRP2"+device.encode()+salt+padded(B)
        request,expected,record=client_exchange(client_pin,host,challenge,device,private=123456789)
        A=int.from_bytes(request[4:260],"big")
        u=int.from_bytes(H(padded(A)+padded(B)),"big")
        S=pow((A*pow(v,u,N))%N,b,N);key=H(padded(S))
        transcript=device.encode()+host.encode()+salt+padded(A)+padded(B)
        mac=lambda label:hmac.new(key,label+transcript,hashlib.sha256).digest()
        return request,expected,record,mac

    def test_srp_correct_pin_and_derived_credential(self):
        request,expected,record,mac=self.server_exchange()
        self.assertEqual(request[260:],mac(b"client-v2:"))
        self.assertEqual(expected,mac(b"server-v2:"))
        self.assertEqual(record["token"],mac(b"secret-v2:")[:16].hex())
        self.assertEqual(record["device_id"],DEVICE)
        self.assertNotIn(b"0042",request)

    def test_wrong_pin_does_not_authenticate(self):
        request,expected,record,mac=self.server_exchange(client_pin="0043")
        self.assertNotEqual(request[260:],mac(b"client-v2:"))
        self.assertNotEqual(expected,mac(b"server-v2:"))
        self.assertNotEqual(record["token"],mac(b"secret-v2:")[:16].hex())

    def test_invalid_public_and_wrong_identity(self):
        for B in (0,1,N,N+1):
            with self.assertRaises(ValueError):client_exchange("0042",HOST,b"SRP2"+DEVICE.encode()+bytes(16)+padded(B))
        with self.assertRaises(ValueError):client_exchange("0042",HOST,b"SRP2"+DEVICE.encode()+bytes(16)+padded(3),"0"*12)
        for pin in ("42","abcd","００４２"):
            with self.assertRaises(ValueError):client_exchange(pin,HOST,b"SRP2"+DEVICE.encode()+bytes(16)+padded(3))

    def test_ephemeral_exchanges_produce_different_credentials(self):
        challenge=b"SRP2"+DEVICE.encode()+bytes(16)+padded(3)
        first=client_exchange("0042",HOST,challenge)
        second=client_exchange("0042",HOST,challenge)
        self.assertNotEqual(first[0],second[0]);self.assertNotEqual(first[2]["token"],second[2]["token"])

    def test_auto_auth_mutual_proof_and_no_key_on_wire(self):
        client,server=socket.socketpair();errors=[]
        def worker():
            try:
                with server:
                    server.settimeout(2)
                    self.assertEqual(recv_exact(server,36),b"AU2?"+HOST.encode())
                    nonce=bytes(range(32));transcript=DEVICE.encode()+HOST.encode()+nonce
                    server.sendall(b"CHL2"+DEVICE.encode()+nonce)
                    proof=recv_exact(server,68)
                    expected=hmac.new(TOKEN.encode(),b"client"+transcript,hashlib.sha256).hexdigest().encode()
                    self.assertEqual(proof,b"PRF2"+expected);self.assertNotIn(TOKEN.encode(),proof)
                    server.sendall(b"OKA2"+hmac.new(TOKEN.encode(),b"server"+transcript,hashlib.sha256).hexdigest().encode())
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=worker);thread.start()
        with client:
            client.settimeout(2);authenticate(client,HOST,TOKEN,DEVICE)
        thread.join(3)
        if errors:raise errors[0]

    def test_replayed_server_proof_is_rejected(self):
        client,server=socket.socketpair()
        def worker():
            with server:
                recv_exact(server,36);server.sendall(b"CHL2"+DEVICE.encode()+b"b"*32)
                recv_exact(server,68);server.sendall(b"OKA2"+b"0"*64)
        thread=threading.Thread(target=worker);thread.start()
        with client:
            client.settimeout(2)
            with self.assertRaises(ValueError):authenticate(client,HOST,TOKEN,DEVICE)
        thread.join(3)


if __name__=="__main__":unittest.main()
