"""Windows GUI for the ESP32-S3 JPEG desktop receiver."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import mss
from input_control import dpi_aware
from protocol import token_bytes
from streamer import StreamSession
from discovery import discover
from wifi_setup import show_dialog
from computer_presence import ComputerPresence, computer_identity, resolve_receiver, validate_request
from pairing import pair, identity_bytes
from settings_store import load_settings, save_settings, profile_path
from desktop_service import DesktopTray, set_startup
import session_control as lifecycle
from single_instance import SingleInstance

BASE = Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
DEFAULTS = dict(host="",port=47989,token="",monitor=1,quality=60,fps=25,
                resolution="400x240",control=True,toolbar=True,smooth=True,device_id="",host_id="",touch_mode="direct",autostart=False)

class App:
    def __init__(self, root,persist=True):
        self.root=root
        self.persist=persist;self.closing=False;self.tray=None
        self.settings_path=profile_path(BASE) if persist else BASE/"settings.json"
        self.active_request=None;self.pending_request=None;self.pin_dialog=None;self.pin_attempts=0
        self.root.title("Moonlight S3 · JPEG 桌面串流")
        self.root.geometry("800x710")
        self.root.minsize(760,420)
        self.events=queue.Queue()
        self.remote=ComputerPresence(lambda request:self.events.put(("receiver_request",request)),
                                     lambda receiver:self.events.put(("receiver_online",receiver)))
        self.session=self.worker=None
        self.pair_worker=None;self.pairing_busy=False
        self.connection_stop=threading.Event()
        self.devices=[]; self.searching=False
        settings=DEFAULTS.copy()
        settings.update(load_settings(self.settings_path))
        settings["computer_id"]=computer_identity(settings)
        self.pairings=settings.pop("pairings",{})
        if not isinstance(self.pairings,dict): self.pairings={}
        # Old compiled tokens are never migrated into a v2 device authorization.
        record=self.pairings.get(settings.get("device_id",""),{})
        if not isinstance(record,dict):record={}
        settings["token"]=record.get("token","")
        settings["host_id"]=record.get("host_id","")
        # Migrate the initial AP-only default. Users can still enter any manual IP.
        if int(settings.get("network_version",1))<2 and settings.get("host")=="192.168.4.1":
            settings["host"]=""
        settings["network_version"]=2
        self.vars={k:tk.BooleanVar(value=v) if isinstance(v,bool) else tk.StringVar(value=str(v)) for k,v in settings.items()}
        frame=ttk.Frame(root,padding=24); frame.pack(fill="both",expand=True)
        ttk.Label(frame,text="Moonlight S3",font=("Segoe UI",24,"bold")).grid(row=0,column=0,columnspan=4,sticky="w")
        ttk.Label(frame,text="ESP32-S3 触屏云桌面 · JPEG 视频 / 鼠标回传",font=("Microsoft YaHei UI",10)).grid(row=1,column=0,columnspan=4,sticky="w",pady=(0,20))
        self.fields=[]
        ttk.Label(frame,text="局域网接收端").grid(row=2,column=0,sticky="w")
        self.device_var=tk.StringVar()
        self.device_list=ttk.Combobox(frame,textvariable=self.device_var,state="readonly")
        self.device_list.grid(row=2,column=1,columnspan=3,sticky="ew",pady=8)
        self.device_list.bind("<<ComboboxSelected>>",self.select_device)
        self.fields.append((self.device_list,"readonly"))
        self.search_button=ttk.Button(frame,text="搜索局域网",command=self.search)
        self.search_button.grid(row=3,column=1,sticky="w")
        self.fields.append((self.search_button,"normal"))
        setup_button=ttk.Button(frame,text="首次配置 S3 Wi-Fi（USB）",command=lambda:show_dialog(root))
        setup_button.grid(row=3,column=2,columnspan=2,sticky="w")
        self.fields.append((setup_button,"normal"))
        def field(label,key,row,col=0,values=None):
            ttk.Label(frame,text=label).grid(row=row,column=col,sticky="w",padx=(0,12),pady=8)
            widget=ttk.Combobox(frame,textvariable=self.vars[key],values=values,state="readonly",width=21) if values else ttk.Entry(frame,textvariable=self.vars[key],width=24,show="*" if key=="token" else "")
            widget.grid(row=row,column=col+1,sticky="ew",padx=(0,18),pady=8)
            self.fields.append((widget,"readonly" if values else "normal"))
        field("接收端 IP / 主机名","host",4); field("TCP 端口","port",4,2)
        ttk.Label(frame,text="连接方式").grid(row=5,column=0,sticky="w",pady=8)
        pairing_frame=ttk.Frame(frame);pairing_frame.grid(row=5,column=1,sticky="w")
        ttk.Label(pairing_frame,text="在 S3 上选择本机").pack(side="left")
        manager=ttk.Button(pairing_frame,text="已配对设备",command=self.manage_devices)
        manager.pack(side="left",padx=8);self.fields.append((manager,"normal"))
        with mss.MSS() as cap:
            monitors=[str(i) for i in range(1,len(cap.monitors))]
            self.monitor_count=len(monitors)
            details="  /  ".join(f"{i}: {m['width']}×{m['height']}" for i,m in enumerate(cap.monitors[1:],1))
        field("显示器编号","monitor",5,2,monitors)
        field("传输分辨率","resolution",6,values=["400x240","800x480"])
        field("目标 FPS","fps",6,2,["10","15","20","25","30"])
        field("JPEG 质量","quality",7,values=["30","40","50","60","70","80","90"])
        ttk.Label(frame,text=details).grid(row=7,column=2,columnspan=2,sticky="w")
        for col,(key,label) in enumerate((("control","允许触屏控制电脑"),("toolbar","屏幕底部操作栏"))):
            widget=ttk.Checkbutton(frame,text=label,variable=self.vars[key])
            widget.grid(row=8,column=col*2,columnspan=2,sticky="w",pady=14)
            self.fields.append((widget,"normal"))
        smooth=ttk.Checkbutton(frame,text="流畅优先（多缓冲一帧；关闭可减少排队）",variable=self.vars["smooth"])
        smooth.grid(row=9,column=0,columnspan=4,sticky="w")
        self.fields.append((smooth,"normal"))
        ttk.Label(frame,text="在 S3 选择电脑；首次连接时输入屏上 PIN，之后直接进入桌面。\n画质、显示器和触摸模式均在 S3 的电脑设置中调整。\n底部 BACK 右侧 MENU 可暂停、输入文字、重连或断开；断开保留电脑程序。",wraplength=720,justify="left").grid(row=10,column=0,columnspan=4,sticky="w",pady=8)
        actions=ttk.Frame(frame); actions.grid(row=11,column=0,columnspan=4,sticky="w",pady=15)
        self.start_button=ttk.Button(actions,text="开始串流",command=self.start); self.start_button.pack_forget()
        self.stop_button=ttk.Button(actions,text="停止 / 释放鼠标",command=self.stop,state="disabled"); self.stop_button.pack(side="left")
        ttk.Button(actions,text="退出软件",command=self.close).pack(side="left",padx=12)
        ttk.Checkbutton(actions,text="开机后台运行",variable=self.vars["autostart"],command=self.startup_changed).pack(side="left",padx=8)
        self.status=tk.StringVar(value="后台已就绪，请在 S3 选择电脑。关闭此窗口会收起到托盘。")
        ttk.Label(frame,textvariable=self.status,wraplength=720,foreground="#087f8c").grid(row=12,column=0,columnspan=4,sticky="w",pady=10)
        frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)
        root.protocol("WM_DELETE_WINDOW",self.hide)
        self.advanced=[]
        for widget in frame.winfo_children():
            info=widget.grid_info()
            if info and (int(info.get("row",0)) in (2,3,4,6,7,8,9) or (int(info.get("row",0))==5 and int(info.get("column",0))>=2)):
                if int(info.get("row",0)) in (2,3,4,9):self.advanced.append(widget)
                widget.grid_remove()
        self.advanced_visible=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text="显示网络诊断与兼容选项",variable=self.advanced_visible,command=self.toggle_advanced).grid(row=13,column=0,columnspan=4,sticky="w")
        root.geometry("800x440")
        if persist:
            self.tray=DesktopTray(lambda action:self.events.put(("tray",action)),bool(self.vars["autostart"].get()))
            if self.vars["autostart"].get():set_startup(True,Path(__file__).resolve())
        try:self.save_settings()
        except OSError as exc:self.status.set(f"本地设置暂时无法保存：{exc}")
        root.after(100,self.poll)

    def search(self):
        if self.searching: return
        self.searching=True; self.search_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.status.set("正在搜索同一局域网内的接收端……")
        def work():
            try: self.events.put(("discovered",discover()))
            except Exception as exc: self.events.put(("search_error",str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def select_device(self,event=None):
        index=self.device_list.current()
        if 0<=index<len(self.devices):
            device=self.devices[index]
            self.vars["host"].set(device.host); self.vars["port"].set(str(device.port))
            self.vars["device_id"].set(device.identity)
            record=self.pairings.get(device.identity,{})
            self.vars["token"].set(record.get("token",""));self.vars["host_id"].set(record.get("host_id",""))
            self.status.set(f"已选择 {device.name}（{device.identity}），首次输入屏上四位码，之后自动验证。")

    def save_settings(self):
        s={k:v.get() for k,v in self.vars.items()}
        # Credentials belong to the exact device identity, never to a guessed name/IP.
        s.pop("token",None);s.pop("host_id",None)
        s["pairings"]=self.pairings
        if self.persist:save_settings(self.settings_path,s)

    def update_endpoint(self,receiver):
        device=receiver["device_id"];record=self.pairings.get(device)
        if not receiver.get("paired") or not record:return
        changed=(record.get("host"),int(record.get("port",47989)))!=(receiver["host"],int(receiver["port"]))
        record.update(host=receiver["host"],port=int(receiver["port"]),name=receiver["name"])
        if self.vars["device_id"].get()==device:
            changed=changed or self.vars["host"].get()!=receiver["host"] or self.vars["port"].get()!=str(receiver["port"])
            self.vars["host"].set(receiver["host"]);self.vars["port"].set(str(receiver["port"]))
        if changed:
            try:self.save_settings()
            except OSError as exc:self.status.set(f"设备地址已更新，但本地保存失败：{exc}")

    def manage_devices(self):
        dialog=tk.Toplevel(self.root);dialog.title("已配对设备");dialog.geometry("550x310")
        listing=tk.Listbox(dialog,height=9);listing.pack(fill="both",expand=True,padx=16,pady=16)
        identities=[]
        def refresh():
            identities[:]=list(self.pairings);listing.delete(0,"end")
            for device in identities:
                record=self.pairings[device]
                listing.insert("end",f"{record.get('name','Moonlight S3')}  ·  {device}")
        def remove():
            selected=listing.curselection()
            if not selected:return
            device=identities[selected[0]]
            if not messagebox.askyesno("删除配对","删除后，下次串流需要重新输入 PIN。",parent=dialog):return
            record=self.pairings.pop(device,None)
            try:self.save_settings()
            except OSError as exc:
                self.pairings[device]=record;messagebox.showerror("删除失败",str(exc),parent=dialog);return
            if self.active_request and self.active_request["device_id"]==device:
                self.stop();self.close_pin();self.active_request=None
            if self.vars["device_id"].get()==device:
                self.vars["token"].set("");self.vars["host_id"].set("")
            refresh()
        ttk.Button(dialog,text="删除选中设备",command=remove).pack(pady=(0,16));refresh()

    def toggle_advanced(self):
        for widget in self.advanced:
            if self.advanced_visible.get():widget.grid()
            else:widget.grid_remove()
        self.root.geometry("800x780" if self.advanced_visible.get() else "800x440")

    def startup_changed(self):
        try:
            enabled=bool(self.vars["autostart"].get());set_startup(enabled,Path(__file__).resolve())
            if self.tray:self.tray.autostart=enabled
            self.save_settings()
        except OSError as exc:messagebox.showerror("无法设置开机启动",str(exc),parent=self.root)

    def show(self):
        self.root.deiconify();self.root.lift()
        if self.pin_dialog and self.pin_dialog.winfo_exists():self.pin_dialog.lift()

    def hide(self):
        if self.tray and self.tray.available:self.root.withdraw()
        else:self.close()

    def stage(self,phase,reason=0,request=None):
        request=request or self.active_request
        if request:
            self.remote.set_phase(request["device_id"],request["action"],phase,reason)
            logging.info("device=%s request=%08x phase=%s reason=%d",request['device_id'],request['action'],lifecycle.PHASE_LABELS.get(phase,phase),reason)

    def close_pin(self):
        if self.pin_dialog:
            try:self.pin_dialog.destroy()
            except tk.TclError:pass
        self.pin_dialog=None;self.pairing_busy=False

    def pair_requested(self,request):
        if self.pairing_busy:return
        self.active_request=request;self.pairing_busy=True;self.pin_attempts=0;self.stage(lifecycle.PIN)
        self.show();dialog=tk.Toplevel(self.root);self.pin_dialog=dialog
        dialog.title("首次串流需要配对");dialog.geometry("420x230");dialog.transient(self.root)
        ttk.Label(dialog,text=f"{request['name']} 请求连接，输入 S3 屏幕上的四位 PIN：",wraplength=380).pack(padx=20,pady=16)
        value=tk.StringVar();entry=ttk.Entry(dialog,textvariable=value,font=("Segoe UI",22),width=8,justify="center");entry.pack();entry.focus_set()
        self.pin_notice=tk.StringVar(value="配对成功后自动开始，原电脑应用不会被关闭。")
        ttk.Label(dialog,textvariable=self.pin_notice,wraplength=380).pack(pady=12)
        controls=ttk.Frame(dialog);controls.pack()
        def cancel():
            self.stage(lifecycle.DECLINED,lifecycle.USER_CANCEL,request);self.close_pin();self.active_request=None;self.status.set("已取消，S3 可直接重试。")
        def submit():
            pin=value.get()
            if len(pin)!=4 or not pin.isascii() or not pin.isdigit():self.pin_notice.set("请输入四位数字，保留前导0。");return
            if self.pair_worker and self.pair_worker.is_alive():return
            self.pin_attempts+=1;self.stage(lifecycle.VERIFY);self.pin_notice.set("正在验证……")
            computer=self.vars["computer_id"].get()
            def work():
                try:
                    record=pair(request["host"],request["port"],pin,request["device_id"],computer)
                    record.update(host=request["host"],port=int(request["port"]),name=request["name"])
                    self.events.put(("pair_ok",(record,request)))
                except Exception as exc:self.events.put(("pair_error",(str(exc),request)))
            self.pair_worker=threading.Thread(target=work,daemon=True);self.pair_worker.start()
        ttk.Button(controls,text="验证并开始",command=submit).pack(side="left",padx=8)
        ttk.Button(controls,text="取消",command=cancel).pack(side="left",padx=8)
        dialog.bind("<Return>",lambda event:submit());dialog.protocol("WM_DELETE_WINDOW",cancel)

    def receiver_request(self,value):
        current=self.active_request
        if value.get("flow")==3 or value.get("flow")==4:
            if self.pending_request and (self.pending_request['device_id'],self.pending_request['action'])==(value['device_id'],value['action']):self.pending_request=None
            if current and (current["device_id"],current["action"])==(value["device_id"],value["action"]):
                self.stop(notify=False);self.close_pin();self.stage(lifecycle.CANCELLED,request=value);self.active_request=None
                self.status.set("S3 已取消连接。" if value.get("flow")==3 else "连接请求已结束，可在 S3 重试。")
            return
        if self.worker and self.worker.is_alive():
            if current and current["device_id"]==value["device_id"]:
                self.pending_request=value;self.stop(notify=False)
            else:self.stage(lifecycle.FAILED,lifecycle.BUSY,value)
            return
        if self.pairing_busy:
            if not current or current["action"]!=value["action"]:self.stage(lifecycle.FAILED,lifecycle.BUSY,value)
            return
        if value.get("version")!=3:self.status.set("请更新 S3 固件以使用连接状态与本地菜单。");return
        self.active_request=value;self.stage(lifecycle.ACCEPTED)
        self.vars["host"].set(value["host"]);self.vars["device_id"].set(value["device_id"]);self.vars["port"].set(str(value["port"]))
        record=self.pairings.get(value["device_id"],{})
        self.vars["token"].set(record.get("token",""));self.vars["host_id"].set(record.get("host_id",""))
        if value["paired"]:self.start()
        else:self.pair_requested(value)

    def start(self):
        if self.pairing_busy or (self.worker and self.worker.is_alive()):return
        if not self.vars["token"].get() or not self.active_request:
            self.status.set("请在 S3 上扫描并选择这台电脑；首次串流会自动弹出 PIN 窗口。");return
        try:
            s={k:v.get() for k,v in self.vars.items()}
            for key in ("port","monitor","quality","fps","network_version"): s[key]=int(s[key])
            token_bytes(s["token"])
            if not s["host"].strip() or not 1<=s["port"]<=65535: raise ValueError("IP/端口无效")
            identity_bytes(s["host_id"]);identity_bytes(s["device_id"],12)
            request=self.active_request.copy();s["request_id"]=request["action"]
            self.stage(lifecycle.PREPARE)
            self.save_settings()
            self.session=None;self.connection_stop=threading.Event();cancel=self.connection_stop
            def run():
                try:
                    endpoint=resolve_receiver(s)
                    if cancel.is_set():return
                    current=validate_request(s,endpoint,request["action"])
                    if cancel.is_set():return
                    s.update(lifecycle.unpack_options(current["options"]))
                    s.update(host=endpoint.host,port=endpoint.port)
                    self.events.put(("receiver_online",dict(device_id=endpoint.identity,host=endpoint.host,port=endpoint.port,name=endpoint.name,paired=True)))
                    def report(message):
                        if isinstance(message,tuple) and message[0]=="stage":self.stage(message[1],request=request)
                        else:self.events.put(message)
                    self.session=StreamSession(s,report)
                    if cancel.is_set():self.session.stop();return
                    self.session.run()
                    self.stage(lifecycle.STOPPED,lifecycle.USER_CANCEL,request);self.events.put("投屏已断开，电脑上的程序继续运行。")
                except Exception as exc:
                    if not cancel.is_set():self.stage(lifecycle.FAILED,lifecycle.error_reason(exc),request);self.events.put(f"连接中断，可在 S3 重连：{exc}")
                finally: self.events.put(None)
            self.worker=threading.Thread(target=run,daemon=True)
            self.worker.start()
            for widget,_ in self.fields: widget.configure(state="disabled")
            self.start_button.configure(state="disabled"); self.stop_button.configure(state="normal")
            self.status.set("正在按设备身份查找当前地址并自动验证……")
        except Exception as exc: messagebox.showerror("无法启动",str(exc))

    def stop(self,notify=True):
        if notify:self.stage(lifecycle.STOPPED,lifecycle.USER_CANCEL)
        self.connection_stop.set()
        if self.session: self.session.stop()

    def poll(self):
        try:
            while True:
                message=self.events.get_nowait()
                if isinstance(message,tuple):
                    kind,value=message
                    if kind=="receiver_online":
                        self.update_endpoint(value);continue
                    if kind=="tray":
                        if value=="show":self.show()
                        elif value=="quit":self.close();return
                        else:self.vars["autostart"].set(not self.vars["autostart"].get());self.startup_changed()
                        continue
                    if kind in ("pair_ok","pair_error"):
                        record_or_error,request=value
                        still_active=self.active_request and self.active_request["action"]==request["action"] and self.active_request["device_id"]==request["device_id"]
                        if kind=="pair_ok":
                            record=record_or_error;device=record["device_id"]
                            self.pairings[device]={key:record[key] for key in ("host_id","token","name","host","port") if key in record}
                            try:self.save_settings()
                            except OSError as exc:
                                self.stage(lifecycle.FAILED,lifecycle.AUTH,request);self.close_pin();self.active_request=None
                                self.status.set(f"配对凭据保存失败，请检查文件权限后重试：{exc}");continue
                            if still_active:
                                for key in ("device_id","host_id","token","host"):
                                    if key in record:self.vars[key].set(record[key])
                                self.close_pin();self.start()
                        elif still_active and self.pin_dialog:
                            self.pin_notice.set("验证失败，请检查屏上 PIN 后重试，或取消。")
                            self.stage(lifecycle.PIN,lifecycle.AUTH,request)
                            if self.pin_attempts>=5:self.stage(lifecycle.FAILED,lifecycle.EXPIRED,request);self.close_pin()
                        continue
                    if kind=="receiver_request":self.receiver_request(value);continue
                    self.searching=False
                    self.search_button.configure(state="normal"); self.start_button.configure(state="normal")
                    if kind=="discovered":
                        self.devices=value; self.device_var.set("")
                        self.device_list.configure(values=[d.label for d in value])
                        self.status.set(f"发现 {len(value)} 个接收端，请从列表选择。" if value else "未发现接收端：确认两端同一局域网、无客户端隔离；也可手动填写 S3 的 IP。")
                    else: self.status.set("搜索失败："+value)
                elif message is None:
                    for widget,state in self.fields: widget.configure(state=state)
                    self.start_button.configure(state="normal"); self.stop_button.configure(state="disabled")
                else: self.status.set(message);logging.info("%s",message)
        except queue.Empty: pass
        if self.closing:return
        busy=self.pairing_busy or bool(self.worker and self.worker.is_alive())
        self.remote.configure(self.vars["computer_id"].get(),self.pairings,self.vars["host"].get(),self.vars["device_id"].get(),
                              True,busy=busy,active_device=self.active_request["device_id"] if self.active_request else "",monitors=self.monitor_count)
        if self.pending_request and not (self.worker and self.worker.is_alive()):
            pending=self.pending_request;self.pending_request=None;self.receiver_request(pending)
        self.root.after(100,self.poll)

    def close(self):
        self.closing=True;self.close_pin()
        if self.tray:self.tray.close()
        self.remote.close()
        self.stop()
        if (self.worker and self.worker.is_alive()) or (self.pair_worker and self.pair_worker.is_alive()):
            self.root.after(100,self.close)
        else: self.root.destroy()

def main():
    parser=argparse.ArgumentParser(description="Moonlight S3 JPEG desktop host")
    parser.add_argument("--background",action="store_true",help="Run in the system tray")
    parser.add_argument("--gui-smoke",action="store_true",help="Construct GUI and exit without streaming")
    parser.add_argument("--capture-smoke",action="store_true",help="Verify DXGI capture without saving images or connecting to S3")
    args=parser.parse_args()
    instance=SingleInstance()
    if not args.gui_smoke and not args.capture_smoke:
        if not instance.acquire():instance.activate();return
    dpi_aware()
    if not args.gui_smoke and not args.capture_smoke:
        logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s",handlers=[RotatingFileHandler(profile_path(BASE).with_name('diagnostics.log'),maxBytes=1024*1024,backupCount=2,encoding='utf-8')])
    if args.capture_smoke:
        from capture import DesktopCapture
        from protocol import Viewport,content_geometry,encode_frame
        with mss.MSS() as displays:
            monitor=displays.monitors[1]
            viewport=Viewport.fit(monitor)
            _,_,width,height=content_geometry(viewport,"400x240")
            capture=DesktopCapture(monitor,(width,height))
            try:
                for _ in range(3):
                    image=capture.grab()
                    assert image.size==(width,height)
                    assert len(encode_frame(image,viewport))>4
            finally: capture.close()
        return
    root=tk.Tk()
    try:application=App(root,persist=not args.gui_smoke)
    except (ValueError,OSError) as exc:
        messagebox.showerror("无法读取本机配置",str(exc),parent=root);root.destroy();instance.close();return
    if args.background:application.hide()
    if args.gui_smoke:
        application.remote.close()
        # Exercise the packaged JPEG plugin and native codec without screen capture/input.
        import io
        from PIL import Image
        from protocol import Viewport, encode_frame
        view=Viewport.fit(dict(left=0,top=0,width=1920,height=1080))
        for resolution in ("400x240","800x480"):
            jpeg=encode_frame(Image.new("RGB",(1920,1080),"blue"),view,resolution=resolution)
            decoded=Image.open(io.BytesIO(jpeg)); decoded.load()
            assert decoded.size==tuple(map(int,resolution.split("x")))
        show_dialog(root)  # Enumerates ports only; never opens one or writes credentials.
        root.after(500,root.destroy)
    try:root.mainloop()
    finally:instance.close()

if __name__=="__main__": main()
