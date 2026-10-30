"""Explicit hardware benchmark. View-only; never injects Windows input."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from input_control import dpi_aware
from main import DEFAULTS
from streamer import StreamSession
from settings_store import profile_path,load_settings
from device_request import RequestedSession


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial",help="Optional serial port to retain diagnostics during capture")
    parser.add_argument("--host")
    parser.add_argument("--seconds",type=float,default=25)
    parser.add_argument("--resolutions",nargs="+",default=["400x240","800x480"])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--label",default="benchmark")
    parser.add_argument("--low-latency",action="store_true",help="Use two instead of three in-flight frames")
    args=parser.parse_args()
    if args.seconds<=0: parser.error("seconds must be positive")
    dpi_aware()
    settings=DEFAULTS|load_settings(profile_path(ROOT))
    settings.update(settings.get("pairings",{}).get(settings.get("device_id",""),{}))
    settings.update(control=False,quality=60,fps=25,smooth=not args.low_latency)
    if args.host: settings["host"]=args.host
    port=None; monitor=None; done=threading.Event(); serial_lines=[]
    if args.serial:
        import serial
        port=serial.Serial(port=None,baudrate=115200,timeout=.2)
        port.dtr=False; port.rts=False; port.port=args.serial; port.open()
        def read_serial():
            while not done.is_set():
                line=port.readline().decode(errors="replace").strip()
                if line: serial_lines.append(line)
        monitor=threading.Thread(target=read_serial,daemon=True); monitor.start()
        time.sleep(6)
    results=[]
    try:
        for resolution in args.resolutions:
            settings["resolution"]=resolution; reports=[]
            def report(message):
                reports.append(message); print(resolution,message,flush=True)
            with RequestedSession(settings) as permit:
                def progress(message):
                    if isinstance(message,tuple):permit.stage(message[1])
                    else:report(message)
                session=StreamSession(permit.settings,report=progress)
                timer=threading.Timer(args.seconds,session.stop); timer.start()
                start=time.monotonic(); error=None
                try: session.run()
                except Exception as exc: error=str(exc)
                finally: timer.cancel()
            elapsed=time.monotonic()-start
            result=dict(resolution=resolution,seconds=round(elapsed,3),sent=session.sent,
                        acked=session.acked,failed=session.failed,error=error,
                        fps=round(session.acked/elapsed,3),profile=session.profile,reports=reports)
            results.append(result)
            print("RESULT",json.dumps({k:v for k,v in result.items() if k!="reports"}),flush=True)
            time.sleep(1)
    finally:
        done.set()
        if monitor: monitor.join(timeout=2)
        if port: port.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(label=args.label,source="real desktop",quality=60,
            target_fps=25,control=False,smooth=settings["smooth"],results=results,serial=serial_lines),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 1 if any(r["error"] or r["failed"] or not r["acked"] for r in results) else 0


if __name__=="__main__": raise SystemExit(main())
