"""Poll the selected receiver for signed, physical-screen start requests.

Uses outbound unicast UDP on the existing receiver port, so the PC needs no
new incoming listener. Nothing is polled while this GUI is streaming.
"""
import hashlib
import hmac
import re
import secrets
import socket
import threading
from protocol import token_bytes


def query_packet(token, nonce):
    prefix=f"MS3CTL1 {nonce}".encode("ascii")
    return prefix+b" "+hmac.new(token_bytes(token),prefix,hashlib.sha256).hexdigest().encode("ascii")


def parse_response(data, token, nonce, identity=""):
    try:
        tag,echo,device,action,signature=data.decode("ascii").split(" ")
        if (tag!="MS3CTL1" or echo!=nonce or not re.fullmatch(r"[0-9a-f]{12}",device)
                or not re.fullmatch(r"[0-9a-f]{8}",action) or (identity and device!=identity)):
            return None
        prefix=data.rsplit(b" ",1)[0]
        expected=hmac.new(token_bytes(token),prefix,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):return None
        return device,int(action,16)
    except (ValueError,UnicodeError):return None


class ReceiverStart:
    def __init__(self, callback):
        self.callback=callback
        self.stop_event=threading.Event()
        self.settings=("","","",False)
        self.lock=threading.Lock()
        self.seen=set()
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.thread.start()

    def configure(self,host,token,identity="",enabled=True):
        with self.lock:self.settings=(host,token,identity,enabled)

    def close(self):self.stop_event.set()

    def _run(self):
        while not self.stop_event.wait(1):
            with self.lock:host,token,identity,enabled=self.settings
            if not enabled or not host:continue
            try:
                nonce=secrets.token_hex(16)
                target=socket.gethostbyname(host)
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                    sock.settimeout(.25)
                    sock.sendto(query_packet(token,nonce),(target,47990))
                    data,peer=sock.recvfrom(256)
                if peer[0]!=target or peer[1]!=47990:continue
                result=parse_response(data,token,nonce,identity)
                if result and result[1] and result not in self.seen:
                    if len(self.seen)>=64:self.seen.clear()
                    self.seen.add(result)
                    self.callback(peer[0],result[0])
            except (OSError,ValueError):pass
