$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# Reuse the installed Python. No venv is created.
python tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
python -m PyInstaller --noconfirm --clean --windowed --onedir --exclude-module cv2 --exclude-module psutil --collect-all dxcam --hidden-import comtypes.stream --distpath dist-release --workpath build/release --specpath build --name MoonlightS3Host main.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
python tools\package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed' }
