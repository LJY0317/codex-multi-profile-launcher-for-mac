"""Safety tests that never touch real ChatGPT or Codex profile data."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "codex_profile", ROOT / "src/codex_profile.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="codex-alt-test-", dir=ROOT
        )
        self.home = Path(self.tmp.name)
        (self.home / "Applications").mkdir()
        (self.home / "Library/Application Support").mkdir(parents=True)
        self.fake_app = self.home / "OfficialChatGPT.app"
        fake_executable = self.fake_app / "Contents/MacOS/ChatGPT"
        fake_executable.parent.mkdir(parents=True)
        fake_executable.touch()
        fake_icon = self.fake_app / "Contents/Resources/electron.icns"
        fake_icon.parent.mkdir(parents=True)
        fake_icon.write_bytes(b"official-icon-fixture")
        self.app_patch = patch.object(module, "APP", self.fake_app)
        self.app_patch.start()
        self.profile = module.Profile(self.home)
        for name in [".codex", "Library/Application Support/Codex"]:
            directory = self.home / name
            directory.mkdir()
            (directory / "sentinel").write_text("original")
        self.fingerprint_patch = patch.object(
            module, "fingerprint", return_value={"fixture": "unchanged"}
        )
        self.fingerprint_patch.start()
        self.running_patch = patch.object(
            module.Profile, "running", return_value=[]
        )
        self.running_patch.start()

    def tearDown(self):
        for name in [".codex", "Library/Application Support/Codex"]:
            self.assertEqual(
                (self.home / name / "sentinel").read_text(), "original"
            )
        self.running_patch.stop()
        self.fingerprint_patch.stop()
        self.app_patch.stop()
        self.tmp.cleanup()

    def test_install_dry_run_remove_and_repeat(self):
        self.profile.install()
        self.assertEqual(list(self.profile.codex.iterdir()), [])
        self.assertEqual(list(self.profile.data.iterdir()), [])
        launcher = (
            self.profile.wrapper / "Contents/MacOS/launcher"
        ).read_text()
        self.assertIn("exec python3", launcher)
        self.assertNotIn(str(Path.home()), launcher)
        self.assertEqual(
            (self.profile.wrapper / "Contents/Resources/icon.icns").read_bytes(),
            b"official-icon-fixture",
        )
        self.profile.uninstall()
        self.assertTrue(self.profile.wrapper.exists())
        # An internal symlink must not cause target deletion.
        (self.profile.data / "outside").symlink_to(
            self.home / ".codex", target_is_directory=True
        )
        self.profile.uninstall(True)
        self.assertTrue(
            all(
                not path.exists()
                for path in self.profile.paths + [self.profile.meta]
            )
        )
        self.profile.install()
        self.profile.uninstall(True)

    def test_existing_profile_refused(self):
        self.profile.codex.mkdir()
        (self.profile.codex / "keep").write_text("keep")
        with self.assertRaises(RuntimeError):
            self.profile.install()
        self.assertFalse(self.profile.meta.exists())
        self.assertEqual((self.profile.codex / "keep").read_text(), "keep")

    def test_symlink_refused(self):
        self.profile.codex.symlink_to(
            self.home / ".codex", target_is_directory=True
        )
        with self.assertRaises(RuntimeError):
            self.profile.install()

    def test_manifest_protected_path_refused(self):
        self.profile.install()
        manifest = self.profile.load()
        manifest["created"][0]["path"] = str(self.home / ".codex")
        self.profile.save(manifest)
        with self.assertRaises(RuntimeError):
            self.profile.uninstall(True)
        self.assertTrue(self.profile.wrapper.exists())

    def test_replaced_directory_refused(self):
        self.profile.install()
        self.profile.data.rename(self.home / "preserved-data")
        self.profile.data.mkdir()
        with self.assertRaises(RuntimeError):
            self.profile.uninstall(True)
        self.assertTrue(self.profile.wrapper.exists())

    def test_running_profile_refused(self):
        self.profile.install()
        with patch.object(module.Profile, "running", return_value=[123]):
            with self.assertRaises(RuntimeError):
                self.profile.uninstall(True)
        self.assertTrue(self.profile.wrapper.exists())

    def test_parent_symlink_refused(self):
        (self.home / "Applications").rmdir()
        (self.home / "Applications").symlink_to(
            self.home / ".codex", target_is_directory=True
        )
        with self.assertRaises(RuntimeError):
            self.profile.install()

    def test_default_launcher_has_its_own_bundle_and_never_reuses_account2(self):
        self.profile.meta.mkdir()
        default = module.DefaultProfileLauncher(self.home)
        default.install()
        info = (default.wrapper / "Contents/Info.plist").read_bytes()
        self.assertIn(b"local.codex-multi-profile-launcher.account1", info)
        self.assertTrue((default.wrapper / "Contents/Resources/icon.icns").exists())
        self.assertNotIn("--user-data-dir=", (default.wrapper / "Contents/MacOS/launcher").read_text())

    def test_default_running_ignores_account2_and_duplicate_default(self):
        default = module.DefaultProfileLauncher(self.home)
        executable = str(self.fake_app / "Contents/MacOS/ChatGPT")
        rows = (
            f"101 {executable} --user-data-dir={self.home}/account2\n"
            f"202 {executable}\n"
        )
        with patch.object(module.subprocess, "check_output", return_value=rows):
            self.assertEqual(default.running(), [202])


if __name__ == "__main__":
    unittest.main()
