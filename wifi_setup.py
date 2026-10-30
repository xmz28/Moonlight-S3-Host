"""Explicit USB configuration: saves Wi-Fi on S3; never flashes firmware."""
import re
import time
import serial

def credentials_command(ssid,password):
    ssid_bytes=ssid.encode("utf-8"); password_bytes=password.encode("utf-8")
    if not 1<=len(ssid_bytes)<=32 or b"\0" in ssid_bytes:
        raise ValueError("Wi-Fi 名称应为 1–32 字节，不能包含空字符")
    length=len(password_bytes)
    if b"\0" in password_bytes or not (length==0 or 8<=length<=63 or
            (length==64 and re.fullmatch(rb"[0-9a-fA-F]{64}",password_bytes))):
        raise ValueError("Wi-Fi 密码应为 8–63 字节；开放网络留空，或输入64位十六进制PSK")
    return b"MS3WIFI1 "+ssid_bytes.hex().encode()+b" "+(password_bytes.hex().encode() or b"-")+b"\n"

def provision(port,ssid,password,serial_factory=serial.Serial):
    command=credentials_command(ssid,password)
    # Set line states before open. Some USB bridge drivers may still pulse reset.
    with serial_factory(port=None,baudrate=115200,timeout=0.15,write_timeout=2) as device:
        device.dtr=False; device.rts=False; device.port=port; device.open()
        deadline=time.monotonic()+8; next_query=0; recognized=False
        while time.monotonic()<deadline:
            if time.monotonic()>=next_query:
                device.write(b"MS3STATUS1\n"); next_query=time.monotonic()+0.7
            reply=device.readline(256).strip()
            if re.fullmatch(rb"MS3STATUS1 [0-9a-f]{12} [0-9.]+ (CONNECTED|WAITING|UNCONFIGURED)",reply):
                recognized=True; break
        if not recognized: raise TimeoutError("未识别到 Moonlight S3，请确认端口、固件和串口占用")
        device.write(command); device.flush()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            reply=device.readline(256).strip()
            if reply==b"MS3WIFI1 OK RESTART": return
            if reply.startswith(b"MS3WIFI1 ERROR"):
                raise ValueError("S3 拒绝保存 Wi-Fi 配置："+reply.decode("ascii",errors="replace"))
        raise TimeoutError("未收到保存确认；请检查串口后重试")

def show_dialog(parent):
    import queue
    import threading
    import tkinter as tk
    from tkinter import ttk
    from serial.tools import list_ports
    window=tk.Toplevel(parent); window.title("S3 首次配置 Wi-Fi（USB）")
    window.geometry("540x330"); window.transient(parent)
    frame=ttk.Frame(window,padding=20); frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="给 S3 保存路由器的 2.4 GHz Wi-Fi；以后独立联网，无需 USB。",wraplength=490).grid(row=0,column=0,columnspan=2,pady=8)
    ports=[p.device for p in list_ports.comports()]
    port=tk.StringVar(value=ports[0] if len(ports)==1 else "")
    ssid=tk.StringVar(); password=tk.StringVar()
    widgets=[]
    for row,label,var in ((1,"USB 串口",port),(2,"Wi-Fi 名称",ssid),(3,"Wi-Fi 密码",password)):
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky="w",pady=8)
        widget=ttk.Combobox(frame,textvariable=var,values=ports) if row==1 else ttk.Entry(frame,textvariable=var,show="*" if row==3 else "",width=35)
        widget.grid(row=row,column=1,sticky="ew",pady=8); widgets.append(widget)
    status=tk.StringVar(value="请关闭占用该串口的监视器。保存后 S3 会重启；不会烧录固件。")
    ttk.Label(frame,textvariable=status,wraplength=490).grid(row=5,column=0,columnspan=2,pady=12)
    events=queue.Queue(); busy=False
    def save():
        nonlocal busy
        try:
            args=(port.get().strip(),ssid.get(),password.get())
            if not args[0]: raise ValueError("请选择明确的 S3 串口")
            credentials_command(args[1],args[2])
        except ValueError as exc: status.set(str(exc)); return
        busy=True; button.configure(state="disabled")
        for widget in widgets: widget.configure(state="disabled")
        status.set("正在识别 S3 并保存配置……")
        def worker():
            try: provision(*args); events.put("已保存，S3 正在重启连接路由器。回到主界面搜索接收端。")
            except Exception as exc: events.put(str(exc))
        threading.Thread(target=worker,daemon=True).start()
    button=ttk.Button(frame,text="保存到 S3",command=save); button.grid(row=4,column=1,sticky="w",pady=8)
    def poll():
        nonlocal busy
        try:
            status.set(events.get_nowait()); password.set(""); busy=False
            button.configure(state="normal")
            for widget in widgets: widget.configure(state="normal")
        except queue.Empty: pass
        window.after(100,poll)
    def close():
        if not busy: window.destroy()
    window.protocol("WM_DELETE_WINDOW",close); window.after(100,poll)
    window.grab_set()
