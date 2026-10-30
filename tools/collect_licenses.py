from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

root=Path(__file__).resolve().parents[1]
dest=root/"licenses"
dest.mkdir(exist_ok=True)
for name in ("Pillow","mss","pyinstaller","pyserial","dxcam","comtypes","numpy"):
    dist=distribution(name)
    for entry in dist.files:
        if "/licenses/" in str(entry) or "license" in Path(str(entry)).name.lower():
            shutil.copyfile(dist.locate_file(entry),dest/(name+"-"+Path(str(entry)).name+".txt"))
python_license=Path(sys.base_prefix)/"LICENSE.txt"
if python_license.exists(): shutil.copyfile(python_license,dest/"Python-LICENSE.txt")
for entry in (Path(sys.base_prefix)/"tcl").rglob("license*"):
    if entry.is_file(): shutil.copyfile(entry,dest/(entry.parent.name+"-"+entry.name))
print("Third-party license notices collected.")
