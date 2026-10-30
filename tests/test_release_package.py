"""Validate the release boundary with fake binaries and local credentials."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.package_release import package


class ReleasePackageTests(unittest.TestCase):
    def prepare(self, root):
        app = root / "dist-release/MoonlightS3Host"
        app.mkdir(parents=True)
        (app / "MoonlightS3Host.exe").write_bytes(b"fake executable")
        for name in ("README.md", "RELEASING.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md"):
            (root / name).write_text("Notice", encoding="utf-8")
        (root / "licenses").mkdir()
        (root / "licenses/license.txt").write_text("License", encoding="utf-8")
        return app

    @patch("tools.package_release.subprocess.check_output", side_effect=["abc123\n", " M build.ps1\n"])
    def test_archive_excludes_credentials_and_preserves_development_settings(self, _git):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.prepare(root)
            development = root / "dist/MoonlightS3Host/settings.json"
            development.parent.mkdir(parents=True)
            for path in (root / "settings.json", development, app / "settings.json"):
                path.write_text('local-pairing-secret', encoding="utf-8")
            package(root)
            self.assertEqual(development.read_text(), "local-pairing-secret")
            self.assertEqual((root / "settings.json").read_text(), "local-pairing-secret")
            archive = root / "dist-release/MoonlightS3Host-windows.zip"
            with zipfile.ZipFile(archive) as bundle:
                self.assertFalse(any(name.endswith("settings.json") for name in bundle.namelist()))
                self.assertIn(b"modified", bundle.read("MoonlightS3Host/SOURCE.txt"))
                self.assertIn("MoonlightS3Host/licenses/license.txt", bundle.namelist())
                self.assertFalse(any(b"local-pairing-secret" in bundle.read(name) for name in bundle.namelist()))
            self.assertTrue((root / "dist-release/SHA256SUMS.txt").read_text().startswith(
                hashlib.sha256(archive.read_bytes()).hexdigest()))

    @patch("tools.package_release.subprocess.check_output", side_effect=["abc123\n", ""])
    def test_nested_config_rejected(self, _git):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.prepare(root)
            (app / "_internal").mkdir()
            (app / "_internal/settings.json").write_text("secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                package(root)
            self.assertFalse((root / "dist-release/MoonlightS3Host-windows.zip").exists())
