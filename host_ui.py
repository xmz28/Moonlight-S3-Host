"""Compact host UI; discovery, pairing and streaming remain owned by App."""
import os
import socket
import tkinter as tk
from tkinter import ttk
import session_control as lifecycle


def build_main(app):
    root=app.root;root.geometry('720x520');root.minsize(680,500)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=('Microsoft YaHei UI',10))
    style.configure('TFrame',background='#f3f5f7')
    style.configure('TLabel',background='#f3f5f7',foreground='#172b3a')
    style.configure('TButton',padding=(12,7))
    style.configure('Card.TFrame',background='#ffffff')
    style.configure('Card.TLabel',background='#ffffff',foreground='#172b3a')
    style.configure('Muted.TLabel',foreground='#617181')
    style.configure('CardMuted.TLabel',background='#ffffff',foreground='#617181')
    style.configure('Accent.TButton',background='#087f8c',foreground='#ffffff',borderwidth=0)
    style.map('Accent.TButton',background=[('disabled','#dce3e8'),('active','#096c77')],foreground=[('disabled','#82909b')])
    app.connection_state=tk.StringVar(value='后台就绪')
    app.receiver_text=tk.StringVar(value='等待 S3 连接')
    app.status=tk.StringVar(value='在 S3 上选择这台电脑；首次连接会自动弹出 PIN 窗口。')
    app.metrics=tk.StringVar(value='开始串流后显示帧率、解码和帧确认信息。')
    app.displayed_request=None;app.settings_dialog=None
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    header=ttk.Frame(frame);header.pack(fill='x',pady=(0,18))
    ttk.Label(header,text='Moonlight S3',font=('Segoe UI',21,'bold')).pack(side='left')
    ttk.Button(header,text='设置',command=app.show_settings).pack(side='right')
    ttk.Button(header,text='已配对设备',command=app.manage_devices).pack(side='right',padx=8)
    card=ttk.Frame(frame,style='Card.TFrame',padding=20);card.pack(fill='x')
    top=ttk.Frame(card,style='Card.TFrame');top.pack(fill='x')
    ttk.Label(top,text='连接状态',style='CardMuted.TLabel').pack(side='left')
    ttk.Label(top,textvariable=app.connection_state,style='Card.TLabel',foreground='#087f8c').pack(side='right')
    ttk.Label(card,textvariable=app.receiver_text,style='Card.TLabel',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',pady=(10,8))
    ttk.Label(card,textvariable=app.status,style='CardMuted.TLabel',wraplength=590,justify='left').pack(fill='x')
    metrics=ttk.Frame(frame,style='Card.TFrame',padding=20);metrics.pack(fill='x',pady=14)
    ttk.Label(metrics,text='会话统计',style='CardMuted.TLabel').pack(anchor='w')
    ttk.Label(metrics,textvariable=app.metrics,style='Card.TLabel',wraplength=590,justify='left',padding=(0,10,0,0)).pack(fill='x')
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=(2,12))
    app.stop_button=ttk.Button(actions,text='断开串流',command=app.stop,style='Accent.TButton',state='disabled')
    app.stop_button.pack(side='left')
    ttk.Button(actions,text='收起到托盘',command=app.hide).pack(side='right')
    more=ttk.Menubutton(actions,text='更多');more.pack(side='right',padx=8)
    menu=tk.Menu(more,tearoff=False);menu.add_command(label='连接诊断',command=app.show_diagnostics)
    menu.add_separator();menu.add_command(label='退出软件',command=app.close);more.configure(menu=menu)
    ttk.Label(frame,text='关闭窗口会收起到托盘，仍可响应 S3 的连接。',style='Muted.TLabel').pack(anchor='w')


def show_settings(app):
    if app.settings_dialog and app.settings_dialog.winfo_exists():app.settings_dialog.lift();return
    dialog=tk.Toplevel(app.root);app.settings_dialog=dialog;dialog.title('运行设置');dialog.geometry('540x380');dialog.resizable(False,False);dialog.transient(app.root)
    frame=ttk.Frame(dialog,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='运行设置',font=('Microsoft YaHei UI',15,'bold')).pack(anchor='w',pady=(0,18))
    ttk.Checkbutton(frame,text='登录 Windows 后在后台运行',variable=app.vars['autostart'],command=app.startup_changed).pack(anchor='w')
    ttk.Label(frame,text='启动后收起到托盘，等待 S3 发起连接。',style='Muted.TLabel').pack(anchor='w',pady=(4,18))
    smooth=ttk.Checkbutton(frame,text='流畅优先',variable=app.vars['smooth'],command=app.preference_changed)
    smooth.pack(anchor='w')
    if app.worker and app.worker.is_alive():smooth.configure(state='disabled')
    ttk.Label(frame,text='多缓冲一帧；关闭可减少排队。下次连接时生效。',style='Muted.TLabel').pack(anchor='w',pady=(4,18))
    ttk.Separator(frame).pack(fill='x',pady=(0,12))
    ttk.Label(frame,text='画质、显示器与触摸选项请在 S3 上设置。',style='Muted.TLabel').pack(anchor='w')
    ttk.Button(frame,text='完成',command=dialog.destroy).pack(anchor='e',pady=(14,0))


def show_diagnostics(app):
    dialog=tk.Toplevel(app.root);dialog.title('连接诊断');dialog.geometry('620x350');dialog.transient(app.root)
    frame=ttk.Frame(dialog,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='连接诊断',font=('Microsoft YaHei UI',15,'bold')).pack(anchor='w',pady=(0,12))
    values=(('电脑',socket.gethostname()),('电脑身份',app.vars['computer_id'].get()),
            ('接收端',app.vars['device_id'].get() or '尚未连接'),
            ('最近地址',app.vars['host'].get() or '自动发现'),('TCP端口',app.vars['port'].get()))
    for label,value in values:
        line=ttk.Frame(frame);line.pack(fill='x',pady=3)
        ttk.Label(line,text=label,width=10,style='Muted.TLabel').pack(side='left')
        ttk.Label(line,text=value).pack(side='left')
    ttk.Label(frame,text='地址随设备身份自动更新；无需因 IP 变化重新配对。',style='Muted.TLabel').pack(anchor='w',pady=14)
    actions=ttk.Frame(frame);actions.pack(fill='x')
    ttk.Button(actions,text='打开日志目录',command=lambda:os.startfile(str(app.settings_path.parent))).pack(side='left')
    ttk.Button(actions,text='关闭',command=dialog.destroy).pack(side='right')


def apply_phase(app,phase,request):
    key=(request['device_id'],request['action'])
    if app.active_request and key!=(app.active_request['device_id'],app.active_request['action']):return
    if not app.active_request and app.displayed_request and key!=app.displayed_request:return
    app.displayed_request=key;app.connection_state.set(lifecycle.PHASE_LABELS.get(phase,'后台就绪'))
    app.receiver_text.set(request.get('name','ESP32-S3'))
    if phase in (lifecycle.ACCEPTED,lifecycle.PREPARE):app.metrics.set('正在建立会话…')


def show_message(app,message):
    if message.startswith('显示 '):
        parts=message.split(' | ');app.metrics.set(' · '.join(parts[:3])+'\n'+' · '.join(parts[3:]));return
    if message.startswith('本地菜单已打开'):app.connection_state.set('已暂停')
    elif message.startswith('已继续桌面'):app.connection_state.set('正在串流')
    app.status.set(message)

