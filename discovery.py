"""LAN discovery. Broadcasts are hints, not pairing/authentication."""
from dataclasses import dataclass
import ipaddress
import re
import secrets
import select
import socket
import time

PORT=47990

@dataclass(frozen=True)
class Device:
    identity: str
    name: str
    host: str
    port: int

    @property
    def label(self):
        return f"{self.name}  ·  {self.host}  ·  {self.identity}"

def parse_reply(data, peer, nonce):
    if len(data)>192: return None
    try:
        tag,echo,identity,port,name=data.decode("ascii").split(" ")
        address=ipaddress.IPv4Address(peer[0])
        port=int(port)
    except (ValueError,UnicodeError): return None
    if (tag!="MS3HERE1" or echo!=nonce or not re.fullmatch(r"[0-9a-f]{12}",identity)
        or name!="moonlight-s3-"+identity[-6:] or not 1<=port<=65535
        or address.is_multicast or address.is_unspecified or str(address)=="255.255.255.255"):
        return None
    return Device(identity,name,str(address),port)

def local_addresses():
    # Binding each NIC makes limited broadcast usable on wired + wireless PCs.
    addresses={"0.0.0.0"}
    try:
        for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET,socket.SOCK_DGRAM):
            ip=item[4][0]
            if not ip.startswith("127."): addresses.add(ip)
    except OSError: pass
    return sorted(addresses)

def discover(timeout=2.5, targets=None, bind_addresses=None):
    targets=targets or [("255.255.255.255",PORT)]
    nonce=secrets.token_hex(16)
    query=("MS3DISC1 "+nonce).encode("ascii")
    sockets=[]; found={}
    try:
        for address in (local_addresses() if bind_addresses is None else bind_addresses):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
                sock.bind((address,0)); sock.setblocking(False); sockets.append(sock)
            except OSError: sock.close()
        if not sockets: raise OSError("无法打开局域网发现接口")
        deadline=time.monotonic()+timeout; next_send=0
        while time.monotonic()<deadline:
            now=time.monotonic()
            if now>=next_send:
                for sock in sockets:
                    for target in targets:
                        try: sock.sendto(query,target)
                        except OSError: pass
                next_send=now+0.6
            ready,_,_=select.select(sockets,[],[],min(0.15,max(0,deadline-time.monotonic())))
            for sock in ready:
                try: data,peer=sock.recvfrom(512)
                except OSError: continue
                device=parse_reply(data,peer,nonce)
                if device:
                    # Do not silently replace one physical identity with a same-named device.
                    found[(device.identity,device.host,device.port)]=device
        return sorted(found.values(),key=lambda d:(d.name,d.host,d.port))
    finally:
        for sock in sockets: sock.close()
