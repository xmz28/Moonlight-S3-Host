"""Diagnostic tools obey the same physical request gate as the GUI."""
import queue
import socket
from computer_presence import ComputerPresence,computer_identity,probe_receiver
from discovery import Device
from single_instance import SingleInstance
from session_control import PREPARE,STOPPED,USER_CANCEL


class RequestedSession:
    def __init__(self,settings,timeout=120):
        self.settings=settings.copy();self.timeout=timeout;self.request=None
        self.events=queue.Queue();self.presence=ComputerPresence(self.events.put)
        self.instance=SingleInstance()

    def __enter__(self):
        s=self.settings
        if not self.instance.acquire():raise RuntimeError('请先在托盘退出电脑软件，再运行独立测试工具。')
        self.presence.configure(computer_identity(s),s.get('pairings',{}),s.get('host',''),s.get('device_id',''))
        print('请在 S3 点这台电脑，允许本次测试（请先退出正常电脑端软件）。',flush=True)
        try:
            while True:
                request=self.events.get(timeout=self.timeout)
                if request.get('flow')!=1:continue
                if s.get('device_id') and s['device_id']!=request['device_id']:continue
                if request.get('version')!=3 or not request.get('paired'):raise ValueError('请先使用电脑软件与新版固件完成首次配对。')
                record=s['pairings'][request['device_id']]
                self.request=request;s.update(record,device_id=request['device_id'],host=request['host'],port=request['port'],request_id=request['action'])
                self.presence.set_phase(request['device_id'],request['action'],PREPARE)
                return self
        except BaseException:
            self.presence.close();self.instance.close();raise

    def stage(self,phase):
        r=self.request
        if r:self.presence.set_phase(r['device_id'],r['action'],phase)

    def __exit__(self,*args):
        r=self.request
        try:
            if r:
                self.presence.set_phase(r['device_id'],r['action'],STOPPED,USER_CANCEL)
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                    sock.settimeout(.2)
                    probe_receiver(sock,self.settings['host_id'],Device(r['device_id'],r['name'],r['host'],r['port']),self.settings,dict(phase=STOPPED,reason=USER_CANCEL,action=r['action']))
        except (OSError,ValueError):pass
        finally:self.presence.close();self.instance.close()
