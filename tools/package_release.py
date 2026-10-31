"""Package a clean onedir build without local identities or pairing credentials."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(root=ROOT):
    output = root / "dist-release"
    app = output / "MoonlightS3Host"
    if not (app / "MoonlightS3Host.exe").is_file():
        raise FileNotFoundError("Build dist-release/MoonlightS3Host first")
    # A previous smoke run may have generated settings in this disposable output.
    (app / "settings.json").unlink(missing_ok=True)
    for name in ("README.md", "INSTALL.zh-CN.md", "RELEASING.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(root / name, app / name)
    shutil.copytree(root / "licenses", app / "licenses", dirs_exist_ok=True)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root, text=True)
    (app / "SOURCE.txt").write_text(
        f"Commit: {commit}\nWorking tree: {'modified; review build, not a tagged release' if status else 'clean'}\n"
        "Protocol: MS3 v3 session control / v2 PIN authorization / v1 JPEG framing\n"
        "No settings.json is distributed. Identity uses the fixed per-user profile.\n",
        encoding="utf-8")
    # Inspect the actual staged payload, including files below _internal.
    if any(p.name.lower() in ("settings.json", "config_secrets.h") for p in app.rglob("*")):
        raise ValueError("Local configuration found in release payload")
    archive = output / "MoonlightS3Host-windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Release package: {archive}")


if __name__ == "__main__":
    package()
