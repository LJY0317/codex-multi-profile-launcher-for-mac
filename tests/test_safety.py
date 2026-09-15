"""Safety tests that never touch real ChatGPT or Codex profile data."""

import importlib.util
import json
import os
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

VOLUME_A = "11111111-2222-4333-8444-555555555555"
VOLUME_B = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"


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
        self.volume_uuid_patch = patch.object(
            module, "volume_uuid", return_value=VOLUME_A
        )
        self.volume_uuid_patch.start()
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
        self.volume_uuid_patch.stop()
        self.fingerprint_patch.stop()
        self.app_patch.stop()
        self.tmp.cleanup()

    def make_legacy_manifest(self, legacy_device=987654321):
        self.profile.install()
        current = self.profile.load()
        legacy = dict(current)
        legacy["schema"] = module.LEGACY_MANIFEST_SCHEMA
        legacy["meta_identity"] = [legacy_device, self.profile.meta.stat().st_ino]
        legacy["created"] = [
            {
                "path": entry["path"],
                "identity": [legacy_device, Path(entry["path"]).stat().st_ino],
            }
            for entry in current["created"]
        ]
        legacy.pop("identity_migration", None)
        self.profile.save(legacy)
        return self.profile.manifest.read_bytes()

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

    def test_owner_mismatch_refused(self):
        self.profile.install()
        original_stat = Path.stat

        def wrong_owner(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == self.profile.codex:
                values = list(result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return result

        with patch.object(Path, "stat", wrong_owner):
            with self.assertRaises(RuntimeError):
                self.profile.safe(self.profile.codex)

    def test_manifest_identity_uses_volume_uuid_and_inode_without_device(self):
        self.profile.install()
        manifest = self.profile.load()
        identities = [manifest["meta_identity"]] + [
            entry["identity"] for entry in manifest["created"]
        ]
        for value in identities:
            self.assertEqual(set(value), {"volume_uuid", "inode"})
            self.assertEqual(value["volume_uuid"], VOLUME_A)

    def test_volume_uuid_change_refused(self):
        self.profile.install()
        with patch.object(module, "volume_uuid", return_value=VOLUME_B):
            with self.assertRaises(RuntimeError):
                self.profile.load()

    def test_identity_lookup_failure_refused_without_fallback(self):
        self.profile.install()
        before = self.profile.manifest.read_bytes()
        with patch.object(
            module, "volume_uuid", side_effect=RuntimeError("fixture lookup failed")
        ):
            with self.assertRaises(RuntimeError):
                self.profile.load()
        self.assertEqual(self.profile.manifest.read_bytes(), before)

    def test_legacy_device_change_requires_explicit_recovery_then_succeeds(self):
        legacy_bytes = self.make_legacy_manifest()
        with self.assertRaises(RuntimeError):
            self.profile.load()

        self.profile.recover_identity()
        self.assertEqual(self.profile.manifest.read_bytes(), legacy_bytes)
        self.assertFalse(self.profile.legacy_backup.exists())

        self.profile.recover_identity(True)
        migrated = self.profile.load()
        self.assertEqual(migrated["schema"], module.MANIFEST_SCHEMA)
        self.assertEqual(self.profile.legacy_backup.read_bytes(), legacy_bytes)
        self.assertFalse(
            any(
                identity.get("volume_uuid") != VOLUME_A
                for identity in [migrated["meta_identity"]]
                + [entry["identity"] for entry in migrated["created"]]
            )
        )

        backup_after_first_recovery = self.profile.legacy_backup.read_bytes()
        self.profile.recover_identity(True)
        self.assertEqual(
            self.profile.legacy_backup.read_bytes(), backup_after_first_recovery
        )

    def test_legacy_inode_change_refused(self):
        self.make_legacy_manifest()
        manifest = json.loads(self.profile.manifest.read_text())
        manifest["created"][1]["identity"][1] += 1
        self.profile.save(manifest)
        with self.assertRaises(RuntimeError):
            self.profile.recover_identity(True)
        self.assertFalse(self.profile.legacy_backup.exists())

    def test_legacy_recovery_refuses_paths_on_different_current_volumes(self):
        self.make_legacy_manifest()

        def split_volume(path):
            return VOLUME_B if path == self.profile.data else VOLUME_A

        with patch.object(module, "volume_uuid", side_effect=split_volume):
            with self.assertRaises(RuntimeError):
                self.profile.recover_identity(True)
        self.assertFalse(self.profile.legacy_backup.exists())

    def test_atomic_manifest_save_ignores_stale_temp_file(self):
        self.profile.install()
        stale = self.profile.meta / ".install-manifest.json.stale.tmp"
        stale.write_text("interrupted")
        manifest = self.profile.load()
        self.profile.save(manifest)
        self.assertEqual(self.profile.load(), manifest)

    def test_launch_error_dialog_is_short_and_actionable(self):
        with patch.object(module.subprocess, "run") as run:
            module.show_account2_launch_error(
                RuntimeError("Metadata directory identity changed")
            )
        message = run.call_args.args[0][-1]
        self.assertIn("ChatGPT (2) / Account2", message)
        self.assertIn("recover-identity.sh", message)
        self.assertIn("--adopt-current-volume", message)
        self.assertNotIn("Traceback", message)
        self.assertLess(len(message), 600)

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
        original_app = module.APP
        module.APP = Path("/Applications/ChatGPT.app")
        executable = "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"
        rows = (
            f"101 {executable} --other=1 --user-data-dir={self.home}/account2\n"
            f"202 {executable} --other=1 --user-data-dir={self.home}/Library/Application Support/Codex\n"
            f"303 {executable} --other=1\n"
            f"404 {executable} --user-data-dir {self.home}/account2\n"
        )
        try:
            with patch.object(module.subprocess, "check_output", return_value=rows):
                self.assertEqual(default.running(), [202, 303])
        finally:
            module.APP = original_app

    def test_default_running_process_activates_exact_pid(self):
        default = module.DefaultProfileLauncher(self.home)
        default.meta.mkdir()
        process = {"pid": 202, "profile": "default", "command": "fixture"}
        with patch.object(default, "_processes", return_value=[process]):
            with patch.object(default, "_window_count_and_activate", return_value=1) as activate:
                with patch.object(module.subprocess, "run") as run:
                    default.launch()
        activate.assert_called_once_with(202)
        run.assert_not_called()

    def test_default_running_without_window_reopens_and_rechecks_visibility(self):
        default = module.DefaultProfileLauncher(self.home)
        default.meta.mkdir()
        process = {"pid": 202, "profile": "default", "command": "fixture"}
        with patch.object(default, "_processes", side_effect=[[process], [process]]):
            with patch.object(
                default, "_window_count_and_activate", side_effect=[0, 1]
            ) as activate:
                with patch.object(default, "_visibility", return_value=(True, True)):
                    with patch.object(
                        module.subprocess,
                        "run",
                        return_value=module.subprocess.CompletedProcess([], 0),
                    ) as run:
                        default.launch()
        self.assertEqual(activate.call_args_list[0].args, (202,))
        self.assertEqual(
            run.call_args.args[0][:3], ["/usr/bin/open", "-n", str(module.APP)]
        )


if __name__ == "__main__":
    unittest.main()
