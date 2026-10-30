"""Announce this computer to receivers; handle screen-initiated requests.

Uses outbound discovery and unicast UDP exchanges on existing receiver port47990.
No fixed incoming PC port or additional firewall rule is needed.
"""
import hashlib
import hmac
import re
import secrets
import socket
import threading
import time
from discovery import discover, Device
from pairing import identity_bytes
from protocol import token_bytes
PORT=47990


def computer_identity(settings):
    identity=settings.get("computer_id","")
    if re.fullmatch(r"[0-9a-f]{32}",identity):return identity
    # Preserve the first existing pairing when migrating the previous single-PC UI.
    for record in settings.get("pairings",{}).values():
        if isinstance(record,dict) and re.fullmatch(r"[0-9a-f]{32}",record.get("host_id","")):
            return record["host_id"]
    return secrets.token_hex(16)


def name_hex(name):
    name="".join(c for c in name if ord(c)>=32 and ord(c)!=127).strip() or "Windows PC"
    return name.encode("utf-8")[:48].decode("utf-8",errors="ignore").encode("utf-8").hex()


def announcement(nonce, computer, device, name, record):
    identity_bytes(nonce);identity_bytes(computer);identity_bytes(device,12)
    known=bool(record and record.get("host_id")==computer)
    prefix=f"MS3HOST2 {nonce} {computer} {device} {int(known)} {name_hex(name)} 1".encode("ascii")
    signature=hmac.new(token_bytes(record["token"]),prefix,hashlib.sha256).hexdigest().encode() if known else b"-"
    return prefix+b" "+signature


def parse_status(data, nonce, computer, device, record):
    if len(data)>256:return None
    try:
        tag,echo,pc,receiver,action,mode,signature=data.decode("ascii").split(" ")
        if (tag!="MS3DEV2" or echo!=nonce or pc!=computer or receiver!=device
                or not re.fullmatch(r"[0-9a-f]{8}",action) or mode not in ("0","1")):return None
        if mode=="1":
            if not record or record.get("host_id")!=computer:return None
            expected=hmac.new(token_bytes(record["token"]),data.rsplit(b" ",1)[0],hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected):return None
        elif signature!="-":return None
        return dict(device_id=device,action=int(action,16),paired=mode=="1")
    except (ValueError,UnicodeError):return None


class ComputerPresence:
    def __init__(self,callback):
        self.callback=callback;self.stop_event=threading.Event();self.lock=threading.Lock()
        self.settings=("",{},"","",False);self.seen=set();self.thread=None

    def configure(self,computer,pairings,host="",device="",enabled=True):
        with self.lock:self.settings=(computer,{k:v.copy() for k,v in pairings.items() if isinstance(v,dict)},host,device,enabled)
        if self.thread is None:
            self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def close(self):self.stop_event.set()

    def _run(self):
        devices={};next_search=0
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(.15)
            while not self.stop_event.wait(.6):
                with self.lock:computer,records,manual_host,manual_device,enabled=self.settings
                if not enabled or not computer:continue
                now=time.monotonic()
                if now>=next_search:
                    try:
                        for device in discover(timeout=.65):devices[device.identity]=(device,now)
                    except OSError:pass
                    next_search=now+4
                if manual_host and re.fullmatch(r"[0-9a-f]{12}",manual_device):
                    try:
                        address=socket.gethostbyname(manual_host)
                        devices[manual_device]=(Device(manual_device,"moonlight-s3-"+manual_device[-6:],address,47989),now)
                    except OSError:pass
                devices={key:value for key,value in devices.items() if now-value[1]<12}
                for device,_ in list(devices.values()):
                    if self.stop_event.is_set():break
                    nonce=secrets.token_hex(16);record=records.get(device.identity,{})
                    try:
                        packet=announcement(nonce,computer,device.identity,socket.gethostname(),record)
                        sock.sendto(packet,(device.host,PORT))
                        deadline=time.monotonic()+.2
                        while time.monotonic()<deadline:
                            try:data,peer=sock.recvfrom(512)
                            except socket.timeout:break
                            if peer!=(device.host,PORT):continue
                            result=parse_status(data,nonce,computer,device.identity,record)
                            if result:
                                result.update(host=device.host,port=device.port,name=device.name)
                                key=(device.identity,result["action"])
                                if result["action"] and key not in self.seen:
                                    if len(self.seen)>128:self.seen.clear()
                                    self.seen.add(key);self.callback(result)
                                break
                    except (OSError,ValueError):continue
