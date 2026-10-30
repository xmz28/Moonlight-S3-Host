"""Preserve local identity/credentials when writing an updated network endpoint."""
import json
import os
from pathlib import Path
import tempfile


def profile_path(legacy_base):
    """Stable per-user identity across upgrades/folders. Migrate without erasing legacy."""
    base=Path(os.environ.get("LOCALAPPDATA",Path.home()/"AppData/Local"))/"MoonlightS3Host"
    base.mkdir(parents=True,exist_ok=True)
    destination=base/"settings.json"
    if not destination.exists():
        legacy=Path(legacy_base)/"settings.json"
        if legacy.exists():save_settings(destination,load_settings(legacy))
    return destination


def load_settings(path):
    try:
        value=json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:return {}
    except (ValueError,UnicodeError) as exc:
        raise ValueError("本机 settings.json 无法读取，已保留原文件，未重建电脑身份或清除配对。") from exc
    if not isinstance(value,dict):raise ValueError("本机配置格式无效，已保留原文件及配对信息。")
    return value


def save_settings(path,settings):
    path=Path(path)
    descriptor,name=tempfile.mkstemp(prefix=".settings-",suffix=".tmp",dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8",newline="\n") as output:
            json.dump(settings,output,ensure_ascii=False,indent=2)
            output.write("\n");output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
