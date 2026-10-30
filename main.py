"""Windows GUI for the ESP32-S3 JPEG desktop receiver."""
import argparse
import json
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
from computer_presence import ComputerPresence, computer_identity
from pairing import pair, identity_bytes

BASE = Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
DEFAULTS = dict(host="",port=47989,token="",monitor=1,quality=60,fps=25,
                resolution="400x240",control=True,toolbar=True,smooth=True,device_id="",host_id="")

class App:
    def __init__(self, root):
        self.root=root
        self.root.title("Moonlight S3 · JPEG 桌面串流")
        self.root.geometry("800x710")
        self.root.minsize(760,690)
        self.events=queue.Queue()
        self.remote=ComputerPresence(lambda request:self.events.put(("receiver_request",request)))
        self.session=self.worker=None
        self.pair_worker=None;self.pairing_busy=False
        self.devices=[]; self.searching=False
        settings=DEFAULTS.copy()
        try: settings.update(json.loads((BASE/"settings.json").read_text(encoding="utf-8")))
        except (OSError,ValueError): pass
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
        ttk.Label(frame,text="在 S3 首页扫描并点击电脑；首次连接时，本机会自动弹窗输入 PIN。\n两端接入同一局域网即可，电脑可用网线或 Wi-Fi，无需指定一方开热点。\n底栏 BACK 返回 S3 首页；LEFT / RIGHT / SCROLL / KEYBOARD 控制电脑。",wraplength=720,justify="left").grid(row=10,column=0,columnspan=4,sticky="w",pady=8)
        actions=ttk.Frame(frame); actions.grid(row=11,column=0,columnspan=4,sticky="w",pady=15)
        self.start_button=ttk.Button(actions,text="开始串流",command=self.start); self.start_button.pack(side="left",padx=(0,12))
        self.stop_button=ttk.Button(actions,text="停止 / 释放鼠标",command=self.stop,state="disabled"); self.stop_button.pack(side="left")
        self.status=tk.StringVar(value="待连接。未开始串流时不会捕获或控制桌面。")
        ttk.Label(frame,textvariable=self.status,wraplength=720,foreground="#087f8c").grid(row=12,column=0,columnspan=4,sticky="w",pady=10)
        frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)
        root.protocol("WM_DELETE_WINDOW",self.close)
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
        (BASE/"settings.json").write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")

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
            self.pairings.pop(device,None)
            if self.vars["device_id"].get()==device:
                self.vars["token"].set("");self.vars["host_id"].set("")
            self.save_settings();refresh()
        ttk.Button(dialog,text="删除选中设备",command=remove).pack(pady=(0,16));refresh()

    def pair_requested(self,request):
        if self.pairing_busy or (self.worker and self.worker.is_alive()):return
        self.pairing_busy=True
        # Disable presence immediately, including while Tk runs its modal PIN dialog.
        self.remote.configure(self.vars["computer_id"].get(),self.pairings,enabled=False)
        pin=simpledialog.askstring("首次串流需要配对",f"{request['name']} 请求连接。\n请输入 S3 屏幕上的四位 PIN：",parent=self.root)
        if pin is None:
            self.pairing_busy=False;self.status.set("已取消。可在 S3 上再次选择电脑。");return
        if len(pin)!=4 or not pin.isascii() or not pin.isdigit():
            self.pairing_busy=False;messagebox.showerror("PIN 无效","请输入四位数字，保留开头的0。");return
        for widget,_ in self.fields:widget.configure(state="disabled")
        self.start_button.configure(state="disabled");self.status.set("正在配对，成功后自动开始串流……")
        computer=self.vars["computer_id"].get()
        def work():
            try:
                record=pair(request["host"],request["port"],pin,request["device_id"],computer)
                record.update(host=request["host"],name=request["name"])
                self.events.put(("pair_ok",(record,True)))
            except Exception as exc:self.events.put(("pair_error",str(exc)))
        self.pair_worker=threading.Thread(target=work,daemon=True);self.pair_worker.start()

    def start(self):
        if self.pairing_busy or (self.worker and self.worker.is_alive()):return
        if not self.vars["token"].get():
            self.status.set("请在 S3 上扫描并选择这台电脑；首次串流会自动弹出 PIN 窗口。");return
        try:
            s={k:v.get() for k,v in self.vars.items()}
            for key in ("port","monitor","quality","fps","network_version"): s[key]=int(s[key])
            token_bytes(s["token"])
            if not s["host"].strip() or not 1<=s["port"]<=65535: raise ValueError("IP/端口无效")
            identity_bytes(s["host_id"]);identity_bytes(s["device_id"],12)
            self.save_settings()
            self.session=StreamSession(s,self.events.put)
            def run():
                try:
                    self.session.run()
                    self.events.put("串流已停止，鼠标已释放。")
                except Exception as exc: self.events.put(f"串流结束：{exc}")
                finally: self.events.put(None)
            self.worker=threading.Thread(target=run,daemon=True)
            self.worker.start()
            for widget,_ in self.fields: widget.configure(state="disabled")
            self.start_button.configure(state="disabled"); self.stop_button.configure(state="normal")
            self.status.set("正在自动验证并连接……")
        except Exception as exc: messagebox.showerror("无法启动",str(exc))

    def stop(self):
        if self.session: self.session.stop()

    def poll(self):
        try:
            while True:
                message=self.events.get_nowait()
                if isinstance(message,tuple):
                    kind,value=message
                    if kind in ("pair_ok","pair_error"):
                        self.pairing_busy=False
                        for widget,state in self.fields:widget.configure(state=state)
                        self.start_button.configure(state="normal")
                        if kind=="pair_ok":
                            record,start_after=value;device=record["device_id"]
                            self.pairings[device]={key:record[key] for key in ("host_id","token","name","host") if key in record}
                            for key in ("device_id","host_id","token","host"):
                                if key in record:self.vars[key].set(record[key])
                            try:self.save_settings()
                            except OSError as exc:
                                self.status.set(f"设备已配对，但电脑保存失败：{exc}");continue
                            self.status.set("配对成功，之后会自动验证；可在 S3 或电脑端开始串流。")
                            if start_after:self.start()
                        else:
                            self.status.set(value);messagebox.showerror("连接失败",value,parent=self.root)
                        continue
                    if kind=="receiver_request":
                        if self.pairing_busy or (self.worker and self.worker.is_alive()):continue
                        self.vars["host"].set(value["host"]);self.vars["device_id"].set(value["device_id"])
                        self.vars["port"].set(str(value["port"]))
                        record=self.pairings.get(value["device_id"],{})
                        self.vars["token"].set(record.get("token",""));self.vars["host_id"].set(record.get("host_id",""))
                        if value["paired"]:self.start()
                        else:self.pair_requested(value)
                        continue
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
                else: self.status.set(message)
        except queue.Empty: pass
        self.remote.configure(self.vars["computer_id"].get(),self.pairings,self.vars["host"].get(),self.vars["device_id"].get(),
                              not self.pairing_busy and not self.searching and not (self.worker and self.worker.is_alive()))
        self.root.after(100,self.poll)

    def close(self):
        self.remote.close()
        self.stop()
        if (self.worker and self.worker.is_alive()) or (self.pair_worker and self.pair_worker.is_alive()):
            self.root.after(100,self.close)
        else: self.root.destroy()

def main():
    parser=argparse.ArgumentParser(description="Moonlight S3 JPEG desktop host")
    parser.add_argument("--gui-smoke",action="store_true",help="Construct GUI and exit without streaming")
    parser.add_argument("--capture-smoke",action="store_true",help="Verify DXGI capture without saving images or connecting to S3")
    args=parser.parse_args()
    dpi_aware()
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
    root=tk.Tk(); application=App(root)
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
    root.mainloop()

if __name__=="__main__": main()
