$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# Reuse the installed Python. No venv is created.
python tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
python -m PyInstaller --noconfirm --clean --windowed --onedir --exclude-module cv2 --exclude-module psutil --collect-all dxcam --hidden-import comtypes.stream --name MoonlightS3Host main.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
Copy-Item -LiteralPath settings.json -Destination dist\MoonlightS3Host\settings.json
Copy-Item -LiteralPath README.md -Destination dist\MoonlightS3Host\README.md
Copy-Item -LiteralPath THIRD_PARTY_NOTICES.md -Destination dist\MoonlightS3Host\THIRD_PARTY_NOTICES.md
Copy-Item -LiteralPath licenses -Destination dist\MoonlightS3Host -Recurse -Force
