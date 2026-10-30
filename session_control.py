"""MS3 lifecycle v3. UI stages and receiver-owned options; no per-frame crypto."""
IDLE,ACCEPTED,PIN,VERIFY,PREPARE,FIRST_FRAME,STREAMING,DECLINED,FAILED,STOPPED,CANCELLED=range(11)
NONE,NETWORK,AUTH,BUSY,CAPTURE,INPUT,DECODE,EXPIRED,USER_CANCEL,VERSION=range(10)
PHASE_LABELS={IDLE:"待连接",ACCEPTED:"电脑已响应",PIN:"等待输入 PIN",VERIFY:"正在验证",PREPARE:"正在准备桌面",FIRST_FRAME:"等待首帧",STREAMING:"正在串流",DECLINED:"电脑已取消",FAILED:"连接失败",STOPPED:"串流已断开",CANCELLED:"已取消"}


def error_reason(exc):
    message=str(exc)
    if any(word in message for word in ("输入注入","输入失败","keyboard","SendInput")):return INPUT
    if any(word in message for word in ("JPEG","解码","显示错误")):return DECODE
    if any(word in message for word in ("显示器","抓屏","capture","DXGI")):return CAPTURE
    if any(word in message for word in ("配对","验证","身份","认证")):return AUTH
    return NETWORK


def pack_options(settings):
    mode=1 if settings.get("touch_mode")=="trackpad" else 0
    return (mode | (4 if settings.get("toolbar",True) else 0) | (8 if settings.get("control",True) else 0)
            | (16 if settings.get("resolution","400x240")=="400x240" else 0)
            | (max(1,min(8,int(settings.get("monitor",1))))<<8)
            | (max(30,min(90,int(settings.get("quality",60))))<<16)
            | (max(10,min(30,int(settings.get("fps",25))))<<24))


def unpack_options(value):
    return dict(touch_mode="trackpad" if value&1 else "direct",toolbar=bool(value&4),control=bool(value&8),
                resolution="400x240" if value&16 else "800x480",monitor=max(1,min(8,(value>>8)&15)),
                quality=max(30,min(90,(value>>16)&255)),fps=max(10,min(30,(value>>24)&63)))
