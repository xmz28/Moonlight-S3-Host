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


def receiver_candidates(found, records, host="", identity="", port=47989):
    """Keep all discovered endpoints; a manual hint must never overwrite them."""
    result=list(found)
    seen={(d.identity,d.host,d.port) for d in result}
    hints=[(device,record.get("host",""),record.get("port",47989))
           for device,record in records.items() if isinstance(record,dict)]
    hints.append((identity,host,port))
    for device,address,tcp_port in hints:
        if not address or not re.fullmatch(r"[0-9a-f]{12}",device):continue
        try:
            address=socket.gethostbyname(address);tcp_port=int(tcp_port)
            if not 1<=tcp_port<=65535:continue
        except (OSError,ValueError,TypeError):continue
        key=(device,address,tcp_port)
        if key not in seen:
            result.append(Device(device,"moonlight-s3-"+device[-6:],address,tcp_port));seen.add(key)
    return result


def probe_receiver(sock, computer, device, record,state=None):
    nonce=secrets.token_hex(16)
    sock.sendto(announcement(nonce,computer,device.identity,socket.gethostname(),record,state),(device.host,PORT))
    deadline=time.monotonic()+.2
    while time.monotonic()<deadline:
        try:data,peer=sock.recvfrom(512)
        except socket.timeout:return None
        if peer!=(device.host,PORT):continue
        result=parse_status(data,nonce,computer,device.identity,record)
        if result:
            result.update(host=device.host,port=device.port,name=device.name)
            return result
    return None


def resolve_receiver(settings, timeout=1.2):
    """Locate the exact paired identity and validate its key before returning an IP."""
    identity=settings["device_id"];identity_bytes(identity,12)
    computer=settings["host_id"];identity_bytes(computer)
    record=dict(host_id=computer,token=settings["token"],host=settings.get("host",""),port=settings.get("port",47989))
    try:found=[d for d in discover(timeout=timeout) if d.identity==identity]
    except OSError:found=[]
    candidates=receiver_candidates(found,{identity:record})
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(.15)
        for device in candidates:
            try:status=probe_receiver(sock,computer,device,record)
            except (OSError,ValueError):continue
            if status and status["paired"]:return device
    raise ConnectionError("暂未找到这台已配对的 S3，正在等待设备重新联网；无需因 IP 变化删除配对。")


def validate_request(settings,device,request_id):
    record=dict(host_id=settings["host_id"],token=settings["token"])
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(.3)
        result=probe_receiver(sock,settings["host_id"],device,record,dict(phase=4,action=request_id))
    if not result or not result.get("paired") or result.get("action")!=request_id or result.get("flow") not in (1,2):
        raise ConnectionError("S3 已取消这次连接或请求已过期，请在 S3 重新选择电脑。")
    return result


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


def announcement(nonce, computer, device, name, record,state=None):
    identity_bytes(nonce);identity_bytes(computer);identity_bytes(device,12)
    known=bool(record and record.get("host_id")==computer)
    prefix=(f"MS3HOST2 {nonce} {computer} {device} {int(known)} {name_hex(name)} 1" if state is None else
            f"MS3HOST3 {nonce} {computer} {device} {int(known)} {name_hex(name)} {'B' if state.get('busy') else 'I'} {int(state.get('phase',0))} {int(state.get('action',0)):08x} {int(state.get('reason',0))} {max(1,min(8,int(state.get('monitors',1))))}").encode("ascii")
    signature=hmac.new(token_bytes(record["token"]),prefix,hashlib.sha256).hexdigest().encode() if known else b"-"
    return prefix+b" "+signature


def parse_status(data, nonce, computer, device, record):
    if len(data)>256:return None
    try:
        fields=data.decode("ascii").split(" ")
        modern=len(fields)==9 and fields[0]=="MS3DEV3"
        if modern:tag,echo,pc,receiver,action,mode,options,flow,signature=fields
        elif len(fields)==7:tag,echo,pc,receiver,action,mode,signature=fields
        else:return None
        if (tag not in ("MS3DEV2","MS3DEV3") or echo!=nonce or pc!=computer or receiver!=device
                or not re.fullmatch(r"[0-9a-f]{8}",action) or mode not in ("0","1")):return None
        if mode=="1":
            if not record or record.get("host_id")!=computer:return None
            expected=hmac.new(token_bytes(record["token"]),data.rsplit(b" ",1)[0],hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected):return None
        elif signature!="-":return None
        result=dict(device_id=device,action=int(action,16),paired=mode=="1")
        if modern:
            if not re.fullmatch(r"[0-9a-f]{8}",options) or flow not in ("0","1","2","3","4"):return None
            result.update(options=int(options,16),flow=int(flow),version=3)
        return result
    except (ValueError,UnicodeError):return None


class ComputerPresence:
    def __init__(self,callback,online_callback=None,search_interval=4,poll_interval=.6):
        self.callback=callback;self.stop_event=threading.Event();self.lock=threading.Lock()
        self.settings=("",{},"","",False);self.seen=set();self.thread=None
        self.online_callback=online_callback
        self.search_interval=search_interval;self.poll_interval=poll_interval
        self.progress={};self.busy=False;self.active_device="";self.monitors=1

    def configure(self,computer,pairings,host="",device="",enabled=True,busy=False,active_device="",monitors=1):
        with self.lock:
            self.settings=(computer,{k:v.copy() for k,v in pairings.items() if isinstance(v,dict)},host,device,enabled)
            self.busy=busy;self.active_device=active_device;self.monitors=monitors
        if self.thread is None:
            self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def close(self):self.stop_event.set()

    def set_phase(self,device,action,phase,reason=0):
        with self.lock:self.progress[device]=dict(action=action,phase=phase,reason=reason)

    def _run(self):
        devices={};next_search=0;online={}
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(.15)
            while not self.stop_event.wait(self.poll_interval):
                with self.lock:computer,records,manual_host,manual_device,enabled=self.settings
                if not enabled or not computer:continue
                now=time.monotonic()
                if now>=next_search:
                    try:
                        for device in discover(timeout=.65):devices[(device.identity,device.host,device.port)]=(device,now)
                    except OSError:pass
                    next_search=now+self.search_interval
                devices={key:value for key,value in devices.items() if now-value[1]<12}
                found=[value[0] for value in sorted(devices.values(),key=lambda value:value[1],reverse=True)]
                verified=set()
                for device in receiver_candidates(found,records,manual_host,manual_device):
                    if self.stop_event.is_set():break
                    if device.identity in verified:continue
                    record=records.get(device.identity,{})
                    try:
                        with self.lock:state=dict(self.progress.get(device.identity,{}),busy=self.busy and self.active_device!=device.identity,monitors=self.monitors)
                        result=probe_receiver(sock,computer,device,record,state)
                        if result:
                            endpoint=(device.host,device.port)
                            if result["paired"]:
                                verified.add(device.identity)
                                if online.get(device.identity)!=endpoint:
                                    online[device.identity]=endpoint
                                    if self.online_callback:self.online_callback(result.copy())
                            key=(device.identity,result["action"],result.get("flow",1))
                            if result["action"] and result.get("flow",1) in (1,3,4) and key not in self.seen:
                                if len(self.seen)>128:self.seen.clear()
                                self.seen.add(key);self.callback(result)
                    except (OSError,ValueError):continue
