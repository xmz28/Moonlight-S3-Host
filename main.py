"""Windows GUI for the ESP32-S3 JPEG desktop receiver."""
import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import mss
from input_control import dpi_aware
from protocol import token_bytes
from streamer import StreamSession
from discovery import discover
from wifi_setup import show_dialog

BASE = Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
DEFAULTS = dict(host="",port=47989,token="",monitor=1,quality=60,fps=25,
                resolution="400x240",control=True,toolbar=True,smooth=True)

class App:
    def __init__(self, root):
        self.root=root
        self.root.title("Moonlight S3 · JPEG 桌面串流")
        self.root.geometry("800x710")
        self.root.minsize(760,690)
        self.events=queue.Queue()
        self.session=self.worker=None
        self.devices=[]; self.searching=False
        settings=DEFAULTS.copy()
        try: settings.update(json.loads((BASE/"settings.json").read_text(encoding="utf-8")))
        except (OSError,ValueError): pass
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
        field("配对码","token",5)
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
        ttk.Label(frame,text="电脑和 S3 接入同一局域网即可，电脑可用网线或 Wi-Fi，无需任何一方开热点。\n搜索后选择接收端；找不到时可填写屏幕上的 IP。配对码验证通过后开始串流。\n400×240 优先流畅；800×480 优先清晰。操作栏支持左键、右键、滚动和屏幕键盘。",wraplength=720,justify="left").grid(row=10,column=0,columnspan=4,sticky="w",pady=8)
        actions=ttk.Frame(frame); actions.grid(row=11,column=0,columnspan=4,sticky="w",pady=15)
        self.start_button=ttk.Button(actions,text="开始串流",command=self.start); self.start_button.pack(side="left",padx=(0,12))
        self.stop_button=ttk.Button(actions,text="停止 / 释放鼠标",command=self.stop,state="disabled"); self.stop_button.pack(side="left")
        self.status=tk.StringVar(value="待连接。未开始串流时不会捕获或控制桌面。")
        ttk.Label(frame,textvariable=self.status,wraplength=720,foreground="#087f8c").grid(row=12,column=0,columnspan=4,sticky="w",pady=10)
        frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)
        root.protocol("WM_DELETE_WINDOW",self.close)
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
            self.status.set(f"已选择 {device.name}（{device.identity}），开始串流时验证配对码。")

    def start(self):
        try:
            s={k:v.get() for k,v in self.vars.items()}
            for key in ("port","monitor","quality","fps","network_version"): s[key]=int(s[key])
            token_bytes(s["token"])
            if not s["host"].strip() or not 1<=s["port"]<=65535: raise ValueError("IP/端口无效")
            (BASE/"settings.json").write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
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
            self.status.set("正在连接并验证配对码……")
        except Exception as exc: messagebox.showerror("无法启动",str(exc))

    def stop(self):
        if self.session: self.session.stop()

    def poll(self):
        try:
            while True:
                message=self.events.get_nowait()
                if isinstance(message,tuple):
                    kind,value=message; self.searching=False
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
        self.root.after(100,self.poll)

    def close(self):
        self.stop()
        if self.worker and self.worker.is_alive():
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
    root=tk.Tk(); App(root)
    if args.gui_smoke:
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
