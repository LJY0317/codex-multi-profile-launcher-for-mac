#!/usr/bin/env python3
"""Manage one fixed, empty alternate ChatGPT/Codex profile on macOS."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


IDENTIFIER = "local.codex-multi-profile-launcher.account2"
DEFAULT_IDENTIFIER = "local.codex-multi-profile-launcher.account1"
MANIFEST_SCHEMA = 2
LEGACY_MANIFEST_SCHEMA = 1
APP = Path("/Applications/ChatGPT.app")
HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
SOURCE = Path(__file__).resolve()


class Profile:
    def __init__(self, home=HOME):
        self.home = home
        self.wrapper = home / "Applications/ChatGPT (2).app"
        self.codex = home / ".codex-account2"
        self.data = home / "Library/Application Support/Codex-Account2"
        self.meta = home / "Library/Application Support/CodexMultiProfileLauncher"
        self.manifest = self.meta / "install-manifest.json"
        self.legacy_backup = self.meta / "install-manifest.schema1-backup.json"
        self.paths = [self.wrapper, self.codex, self.data]
        self.protected = [
            APP,
            home / ".codex",
            home / "Library/Application Support/Codex",
        ]

    def safe(self, path):
        if path not in self.paths + [self.meta]:
            raise RuntimeError("Path outside fixed allowlist: " + str(path))
        for candidate in [path, *path.parents]:
            if candidate.is_symlink():
                raise RuntimeError("Symlink path refused: " + str(candidate))
        resolved = path.resolve()
        for protected in self.protected:
            protected_resolved = protected.resolve()
            if (
                resolved == protected_resolved
                or protected_resolved in resolved.parents
                or resolved in protected_resolved.parents
            ):
                raise RuntimeError("Protected path refused")
        if path.exists() and (
            not path.is_dir() or path.stat().st_uid != os.getuid()
        ):
            raise RuntimeError("Expected an owned directory: " + str(path))

    def save(self, manifest):
        atomic_write_json(self.manifest, manifest)

    def _read_manifest(self):
        self.safe(self.meta)
        if not self.manifest.is_file() or self.manifest.is_symlink():
            raise RuntimeError("Install manifest missing or symlinked")
        manifest = json.loads(self.manifest.read_text())
        if manifest.get("id") != IDENTIFIER:
            raise RuntimeError("Unknown manifest")
        return manifest

    def _validate_entries(self, manifest, identity_kind):
        seen = set()
        entries = manifest.get("created")
        if not isinstance(entries, list):
            raise RuntimeError("Invalid manifest entries")
        for entry in entries:
            if not isinstance(entry, dict) or "path" not in entry or "identity" not in entry:
                raise RuntimeError("Invalid manifest entry")
            path = Path(entry["path"])
            self.safe(path)
            if path not in self.paths or str(path) in seen:
                raise RuntimeError("Invalid or duplicate manifest entry")
            seen.add(str(path))
            if not identity_kind(entry["identity"]):
                raise RuntimeError("Invalid directory identity")
        if seen != set(map(str, self.paths)):
            raise RuntimeError("Manifest path set is incomplete")

    def load(self):
        manifest = self._read_manifest()
        if manifest.get("schema") == LEGACY_MANIFEST_SCHEMA:
            raise RuntimeError(
                "Legacy install manifest requires explicit identity recovery; "
                "run recover-identity before launch"
            )
        if manifest.get("schema") != MANIFEST_SCHEMA:
            raise RuntimeError("Unknown manifest")
        if not stable_identity_value(manifest.get("meta_identity")):
            raise RuntimeError("Invalid metadata directory identity")
        if manifest.get("meta_identity") != identity(self.meta):
            raise RuntimeError("Metadata directory identity changed")
        self._validate_entries(manifest, stable_identity_value)
        for entry in manifest["created"]:
            path = Path(entry["path"])
            if path.exists() and identity(path) != entry["identity"]:
                raise RuntimeError("Directory replaced; preserving: " + str(path))
        return manifest

    def recover_identity(self, adopt_current_volume=False):
        manifest = self._read_manifest()
        if manifest.get("schema") == MANIFEST_SCHEMA:
            self.load()
            print("Install manifest already uses APFS Volume UUID + inode identities")
            return
        if manifest.get("schema") != LEGACY_MANIFEST_SCHEMA:
            raise RuntimeError("Unknown manifest")
        if not legacy_identity_value(manifest.get("meta_identity")):
            raise RuntimeError("Invalid legacy metadata identity")
        self._validate_entries(manifest, legacy_identity_value)
        if manifest.get("ready") is not True:
            raise RuntimeError("Legacy installation is incomplete; refusing recovery")

        legacy_identities = [manifest["meta_identity"]] + [
            entry["identity"] for entry in manifest["created"]
        ]
        if len({value[0] for value in legacy_identities}) != 1:
            raise RuntimeError("Legacy manifest recorded multiple devices; refusing recovery")

        current = {str(self.meta): identity(self.meta)}
        if self.meta.stat().st_ino != manifest["meta_identity"][1]:
            raise RuntimeError("Metadata directory inode changed; refusing recovery")
        for entry in manifest["created"]:
            path = Path(entry["path"])
            if not path.is_dir():
                raise RuntimeError("Managed directory missing; refusing recovery: " + str(path))
            if path.stat().st_ino != entry["identity"][1]:
                raise RuntimeError("Directory inode changed; refusing recovery: " + str(path))
            current[str(path)] = identity(path)

        volume_uuids = {value["volume_uuid"] for value in current.values()}
        if len(volume_uuids) != 1:
            raise RuntimeError("Managed paths are on different APFS volumes; refusing recovery")
        volume_uuid_value = next(iter(volume_uuids))

        print("Legacy inode continuity verified for metadata and all managed directories")
        print("Current APFS Volume UUID:", volume_uuid_value)
        print(
            "Legacy manifest has no Volume UUID, so prior-volume continuity "
            "cannot be proven from that record"
        )
        if not adopt_current_volume:
            print(
                "Dry run only. Re-run recover-identity with --adopt-current-volume "
                "to explicitly adopt this verified current volume"
            )
            return

        legacy_bytes = self.manifest.read_bytes()
        create_backup_once(self.legacy_backup, legacy_bytes)
        migrated = dict(manifest)
        migrated["schema"] = MANIFEST_SCHEMA
        migrated["meta_identity"] = current[str(self.meta)]
        migrated["created"] = [
            {"path": entry["path"], "identity": current[entry["path"]]}
            for entry in manifest["created"]
        ]
        migrated["identity_migration"] = {
            "from_schema": LEGACY_MANIFEST_SCHEMA,
            "legacy_backup": self.legacy_backup.name,
            "legacy_volume_uuid_available": False,
            "recovery": "explicit-current-volume-adoption",
        }
        self.save(migrated)
        self.load()
        print("Recovered install manifest:", self.manifest)
        print("Legacy manifest backup:", self.legacy_backup)

    def install(self):
        for path in self.paths + [self.meta]:
            self.safe(path)
            if path.exists():
                raise RuntimeError(
                    "Existing path preserved; install refused: " + str(path)
                )
            if not path.parent.is_dir():
                raise RuntimeError(
                    "Create this parent directory first: " + str(path.parent)
                )
        executable = APP / "Contents/MacOS/ChatGPT"
        if not executable.is_file():
            raise RuntimeError("Official ChatGPT executable missing")
        icon = APP / "Contents/Resources/electron.icns"
        if not icon.is_file():
            raise RuntimeError("Official ChatGPT icon missing")

        baseline = fingerprint()
        self.meta.mkdir(mode=0o700)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "id": IDENTIFIER,
            "meta_identity": identity(self.meta),
            "created": [],
            "official_baseline": baseline,
            "ready": False,
        }
        self.save(manifest)

        # Journal immediately after each exclusive mkdir. Never adopt existing paths.
        for path in self.paths:
            path.mkdir(mode=0o700)
            manifest["created"].append(
                {"path": str(path), "identity": identity(path)}
            )
            self.save(manifest)

        resources = self.wrapper / "Contents/Resources"
        macos = self.wrapper / "Contents/MacOS"
        resources.mkdir(parents=True)
        macos.mkdir()
        shutil.copyfile(SOURCE, resources / "codex_profile.py")
        # Reuse the installed official app icon; do not alter its bundle.
        shutil.copyfile(icon, resources / "icon.icns")
        launcher = (
            "#!/bin/sh\n"
            "set -eu\n"
            "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n"
            "export PATH\n"
            'exec python3 "$(dirname "$0")/../Resources/codex_profile.py" launch\n'
        )
        (macos / "launcher").write_text(launcher)
        (macos / "launcher").chmod(0o755)

        info = {
            "CFBundleIdentifier": IDENTIFIER,
            "CFBundleDisplayName": "ChatGPT (2)",
            "CFBundleName": "ChatGPT (2)",
            "CFBundleExecutable": "launcher",
            "CFBundleIconFile": "icon.icns",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0",
            "LSUIElement": True,
        }
        with (self.wrapper / "Contents/Info.plist").open("wb") as file:
            plistlib.dump(info, file)
        subprocess.run(
            ["plutil", "-lint", str(self.wrapper / "Contents/Info.plist")],
            check=True,
        )

        manifest["ready"] = True
        self.save(manifest)
        if fingerprint() != baseline:
            raise RuntimeError(
                "Official application changed during install; inspect before launch"
            )
        print("Installed:", self.wrapper)

    def running(self):
        # Do not inspect the process environment or print credentials.
        rows = subprocess.check_output(
            ["ps", "-axo", "pid=,args="], text=True
        )
        marker = "--user-data-dir=" + str(self.data)
        return [
            int(row.strip().split(None, 1)[0])
            for row in rows.splitlines()
            if marker in row and "/Applications/ChatGPT.app/Contents/" in row
        ]

    def launch(self):
        manifest = self.load()
        installed_paths = {entry["path"] for entry in manifest["created"]}
        if not manifest["ready"] or installed_paths != set(map(str, self.paths)):
            raise RuntimeError("Installation incomplete")
        if any(not path.is_dir() for path in self.paths):
            raise RuntimeError(
                "Managed directory missing; refusing implicit recreation"
            )

        # Do not inherit account A's Codex, API, Electron, or auth variables.
        username = pwd.getpwuid(os.getuid()).pw_name
        env = {
            "HOME": str(self.home),
            "USER": username,
            "LOGNAME": username,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
            "CODEX_HOME": str(self.codex),
            "CODEX_ELECTRON_USER_DATA_PATH": str(self.data),
        }
        if os.environ.get("TMPDIR"):
            env["TMPDIR"] = os.environ["TMPDIR"]
        executable = str(APP / "Contents/MacOS/ChatGPT")
        os.chdir(self.home)
        os.execve(
            executable,
            [executable, "--user-data-dir=" + str(self.data)],
            env,
        )

    def status(self):
        print("Official app:", APP)
        for path in self.paths + [self.meta]:
            print(str(path), "present" if path.exists() else "absent")
        if self.manifest.exists():
            manifest = self.load()
            print("Installation ready:", manifest["ready"])
            print(
                "Official core files match installation:",
                fingerprint() == manifest["official_baseline"],
            )
            print("Second-profile process IDs:", self.running())
        else:
            print("No installation manifest")

    def uninstall(self, yes=False):
        manifest = self.load()
        if self.running():
            raise RuntimeError(
                "Quit ChatGPT (2) first. No processes will be terminated automatically."
            )
        targets = [
            Path(entry["path"])
            for entry in manifest["created"]
            if Path(entry["path"]).exists()
        ]
        for path in targets:
            # rmtree does not follow internal symlinks. Refuse mounted subtrees.
            for root, dirs, _ in os.walk(path, followlinks=False):
                if os.path.ismount(root):
                    raise RuntimeError("Mounted subtree refused: " + root)
                for directory in dirs:
                    candidate = Path(root) / directory
                    if not candidate.is_symlink() and os.path.ismount(candidate):
                        raise RuntimeError(
                            "Mounted subtree refused: " + str(candidate)
                        )
        print(
            "Remove only these installed paths "
            "(including second-profile conversations/login):"
        )
        for path in targets:
            print(path)
        print(self.manifest)
        if not yes:
            print("Dry run only. To remove: scripts/uninstall.sh --yes")
            return

        # Revalidate every identity before deleting anything.
        self.load()
        for path in targets:
            shutil.rmtree(path)
        self.manifest.unlink()
        try:
            self.meta.rmdir()
        except OSError:
            print("Preserved nonempty metadata directory:", self.meta)
        print("Uninstalled. Official app and default profile were not targeted.")


class DefaultProfileLauncher:
    """A LaunchServices-visible entry point for the protected default profile."""

    def __init__(self, home=HOME):
        self.home = home
        self.wrapper = home / "Applications/ChatGPT (1).app"
        self.meta = home / "Library/Application Support/CodexMultiProfileLauncher"
        self.manifest = self.meta / "default-install-manifest.json"
        self.data = home / "Library/Application Support/Codex"
        self.trace = self.meta / "default-launch.log"

    def install(self):
        if self.wrapper.exists() or self.manifest.exists():
            raise RuntimeError("Existing default launcher preserved; install refused")
        if not self.wrapper.parent.is_dir() or not self.meta.is_dir():
            raise RuntimeError("Create launcher parent directories first")
        executable = APP / "Contents/MacOS/ChatGPT"
        icon = APP / "Contents/Resources/electron.icns"
        if not executable.is_file() or not icon.is_file():
            raise RuntimeError("Official ChatGPT executable or icon missing")
        resources = self.wrapper / "Contents/Resources"
        macos = self.wrapper / "Contents/MacOS"
        resources.mkdir(parents=True, mode=0o700)
        macos.mkdir(mode=0o700)
        shutil.copyfile(SOURCE, resources / "codex_profile.py")
        shutil.copyfile(icon, resources / "icon.icns")
        launcher = (
            "#!/bin/sh\n"
            "set -eu\n"
            "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n"
            "export PATH\n"
            'exec python3 "$(dirname "$0")/../Resources/codex_profile.py" default-launch\n'
        )
        (macos / "launcher").write_text(launcher)
        (macos / "launcher").chmod(0o755)
        info = {
            "CFBundleIdentifier": DEFAULT_IDENTIFIER,
            "CFBundleDisplayName": "ChatGPT (1)",
            "CFBundleName": "ChatGPT (1)",
            "CFBundleExecutable": "launcher",
            "CFBundleIconFile": "icon.icns",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0",
            "LSUIElement": True,
        }
        with (self.wrapper / "Contents/Info.plist").open("wb") as file:
            plistlib.dump(info, file)
        subprocess.run(
            ["plutil", "-lint", str(self.wrapper / "Contents/Info.plist")],
            check=True,
        )
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "id": DEFAULT_IDENTIFIER,
                    "wrapper": str(self.wrapper),
                },
                indent=2,
            )
            + "\n"
        )
        print("Installed:", self.wrapper)

    def update(self):
        if self.wrapper.is_symlink() or not self.wrapper.is_dir():
            raise RuntimeError("Default launcher is missing or symlinked")
        if not self.manifest.is_file() or self.manifest.is_symlink():
            raise RuntimeError("Default launcher manifest missing or symlinked")
        manifest = json.loads(self.manifest.read_text())
        if (
            manifest.get("schema") != 1
            or manifest.get("id") != DEFAULT_IDENTIFIER
            or manifest.get("wrapper") != str(self.wrapper)
        ):
            raise RuntimeError("Unknown default launcher manifest")
        backup_root = self.meta / "backups" / (
            "chatgpt1-" + time.strftime("%Y%m%d-%H%M%S")
        )
        backup_root.parent.mkdir(mode=0o700, exist_ok=True)
        shutil.copytree(self.wrapper, backup_root)
        resources = self.wrapper / "Contents/Resources"
        macos = self.wrapper / "Contents/MacOS"
        if not (resources.is_dir() and macos.is_dir()):
            raise RuntimeError("Default launcher layout is incomplete")
        shutil.copyfile(SOURCE, resources / "codex_profile.py")
        launcher = macos / "launcher"
        launcher.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n"
            "export PATH\n"
            'exec python3 "$(dirname "$0")/../Resources/codex_profile.py" default-launch\n'
        )
        launcher.chmod(0o755)
        manifest["source_sha256"] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        manifest["backup"] = str(backup_root)
        temporary = self.meta / "default-install-manifest.tmp"
        temporary.write_text(json.dumps(manifest, indent=2) + "\n")
        os.replace(temporary, self.manifest)
        print("Updated:", self.wrapper)
        print("Backup:", backup_root)

    def running(self):
        return [process["pid"] for process in self._processes() if process["profile"] == "default"]

    def _processes(self):
        """Return only official ChatGPT main processes with classified data paths."""
        rows = subprocess.check_output(["/bin/ps", "-axo", "pid=,args="], text=True)
        executable = str(APP / "Contents/MacOS/ChatGPT")
        result = []
        for row in rows.splitlines():
            fields = row.strip().split(None, 1)
            if len(fields) != 2:
                continue
            command = fields[1]
            if not (command == executable or command.startswith(executable + " ")):
                continue
            remainder = command[len(executable):].lstrip()
            user_data = []
            for match in re.finditer(
                r"(?<!\S)--user-data-dir(?:=|\s|$)", remainder
            ):
                value = remainder[match.end():]
                next_flag = re.search(r"\s--[A-Za-z0-9][A-Za-z0-9_-]*(?:=|\s|$)", value)
                if next_flag:
                    value = value[:next_flag.start()]
                user_data.append(value.strip() or None)
            profile = "unknown"
            if len(user_data) == 0:
                profile = "default"
            elif len(user_data) == 1 and user_data[0] == str(self.data):
                profile = "default"
            elif len(user_data) == 1 and user_data[0]:
                profile = "other"
            result.append(
                {"pid": int(fields[0]), "profile": profile, "command": command}
            )
        return result

    def _record(self, stage, **fields):
        self.meta.mkdir(mode=0o700, exist_ok=True)
        safe_fields = {"stage": stage, "pid": os.getpid(), **fields}
        with self.trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe_fields, sort_keys=True) + "\n")

    def _window_count_and_activate(self, pid):
        script = (
            'tell application "System Events"\n'
            f"set p to first application process whose unix id is {pid}\n"
            "set frontmost of p to true\n"
            "return count of windows of p\n"
            "end tell"
        )
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            raise RuntimeError("Account1 window probe failed")
        try:
            return int(result.stdout.strip())
        except ValueError as error:
            raise RuntimeError("Account1 window probe returned invalid data") from error

    def _visibility(self, pid):
        info = subprocess.run(
            ["/usr/bin/lsappinfo", "info", "-pid", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if info.returncode != 0:
            return False, False
        asn = re.search(r"ASN:0x[0-9a-f]+-0x[0-9a-f]+-\"[^\"]+\"", info.stdout)
        if not asn:
            return False, False
        visible = subprocess.run(
            ["/usr/bin/lsappinfo", "visibleProcessList"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if visible.returncode != 0:
            return False, False
        index = visible.stdout.find(asn.group(0))
        return index >= 0, index == 0

    def _reopen_existing(self):
        result = subprocess.run(
            [
                "/usr/bin/open",
                "-n",
                str(APP),
                "--args",
                "--user-data-dir=" + str(self.data),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Account1 reopen request failed")
        for _ in range(15):
            processes = self._processes()
            defaults = [p for p in processes if p["profile"] == "default"]
            if len(defaults) == 1:
                visible, frontmost = self._visibility(defaults[0]["pid"])
                if visible and frontmost:
                    return defaults[0]["pid"]
            if len(defaults) > 1:
                raise RuntimeError("Multiple Account1 processes after reopen")
            time.sleep(0.2)
        raise RuntimeError("Account1 reopen did not produce a visible window")

    def launch(self):
        self._record("wrapper_entry")
        processes = self._processes()
        defaults = [p for p in processes if p["profile"] == "default"]
        unknown = [p for p in processes if p["profile"] == "unknown"]
        if unknown:
            self._record("unknown_process_ignored", pids=[p["pid"] for p in unknown])
        if len(defaults) > 1:
            self._record("duplicate_default_process", pids=[p["pid"] for p in defaults])
            raise RuntimeError("Multiple Account1 processes; refusing to select one")
        if defaults:
            pid = defaults[0]["pid"]
            self._record("account1_process_found", target_pid=pid)
            try:
                windows = self._window_count_and_activate(pid)
                self._record("account1_window_probe", target_pid=pid, windows=windows)
                if windows > 0:
                    print("Account1 window activated:", pid)
                    return
            except (RuntimeError, subprocess.TimeoutExpired):
                self._record("account1_window_probe_error", target_pid=pid)
            reopened = self._reopen_existing()
            self._record("account1_window_reopened", target_pid=reopened)
            print("Account1 window reopened:", reopened)
            return
        username = pwd.getpwuid(os.getuid()).pw_name
        env = {
            "HOME": str(self.home),
            "USER": username,
            "LOGNAME": username,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
            "CODEX_HOME": str(self.home / ".codex"),
            "CODEX_ELECTRON_USER_DATA_PATH": str(self.data),
        }
        if os.environ.get("TMPDIR"):
            env["TMPDIR"] = os.environ["TMPDIR"]
        executable = str(APP / "Contents/MacOS/ChatGPT")
        self._record("execve_start", executable=executable)
        os.chdir(self.home)
        try:
            os.execve(executable, [executable, "--user-data-dir=" + str(self.data)], env)
        except OSError as error:
            self._record("execve_error", errno=error.errno, error_type=type(error).__name__)
            raise


def stable_identity_value(value):
    if not isinstance(value, dict) or set(value) != {"volume_uuid", "inode"}:
        return False
    try:
        uuid.UUID(value["volume_uuid"])
    except (AttributeError, TypeError, ValueError):
        return False
    return isinstance(value["inode"], int) and value["inode"] > 0


def legacy_identity_value(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(part, int) and part >= 0 for part in value)
        and value[1] > 0
    )


def volume_uuid(path):
    try:
        df = subprocess.check_output(
            ["/bin/df", "-P", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        lines = [line for line in df.splitlines() if line.strip()]
        if len(lines) < 2:
            raise RuntimeError("Filesystem identity lookup returned no mount data")
        device = lines[-1].split()[0]
        if not device.startswith("/dev/"):
            raise RuntimeError("Managed path is not on a local disk volume")
        output = subprocess.check_output(
            ["/usr/sbin/diskutil", "info", "-plist", device],
            stderr=subprocess.DEVNULL,
        )
        info = plistlib.loads(output)
    except (OSError, plistlib.InvalidFileException, subprocess.SubprocessError) as error:
        raise RuntimeError("APFS volume identity lookup failed") from error
    if info.get("FilesystemType") != "apfs":
        raise RuntimeError("Managed path is not on APFS")
    value = info.get("VolumeUUID")
    try:
        return str(uuid.UUID(value)).upper()
    except (AttributeError, TypeError, ValueError) as error:
        raise RuntimeError("APFS Volume UUID unavailable") from error


def identity(path):
    stat = path.stat()
    return {"volume_uuid": volume_uuid(path), "inode": stat.st_ino}


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path, data):
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path, value):
    data = (json.dumps(value, indent=2) + "\n").encode()
    atomic_write_bytes(path, data)


def create_backup_once(path, data):
    if path.is_symlink():
        raise RuntimeError("Symlink legacy manifest backup refused")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise RuntimeError("Legacy manifest backup already exists with different contents")
        return

    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise RuntimeError(
                    "Legacy manifest backup appeared with different contents"
                )
        _fsync_directory(path.parent)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def show_account2_launch_error(error):
    detail = " ".join(str(error).split())[:240]
    message = (
        "ChatGPT (2) / Account2를 시작하지 못했습니다.\n\n"
        "설치 경로 검증이 필요합니다. 프로젝트에서 "
        "scripts/recover-identity.sh로 확인한 뒤 필요한 경우 "
        "--adopt-current-volume으로 명시 복구하세요.\n\n"
        "오류: " + detail
    )
    script = (
        'on run argv\n'
        'display alert "ChatGPT (2) 실행 실패" message (item 1 of argv) '
        'as critical buttons {"확인"} default button "확인"\n'
        'end run'
    )
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def fingerprint():
    # Read application code only; never read profile contents.
    paths = [
        APP / "Contents/Info.plist",
        APP / "Contents/MacOS/ChatGPT",
        APP / "Contents/Resources/app.asar",
    ]
    return {
        str(path.relative_to(APP)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main():
    os.umask(0o077)
    if sys.platform != "darwin":
        print("Error: this launcher supports macOS only", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "install", "launch", "status", "uninstall", "recover-identity",
            "install-default", "update-default", "default-launch",
        ],
    )
    parser.add_argument(
        "--yes", action="store_true", help="Apply uninstall; default is dry run"
    )
    parser.add_argument(
        "--adopt-current-volume",
        action="store_true",
        help="Explicitly adopt the currently verified APFS volume during legacy recovery",
    )
    args = parser.parse_args()
    if args.command in {"install-default", "update-default", "default-launch"}:
        profile = DefaultProfileLauncher()
        command = {
            "install-default": "install",
            "update-default": "update",
            "default-launch": "launch",
        }[args.command]
    else:
        profile = Profile()
        command = args.command
    try:
        if command == "uninstall":
            profile.uninstall(args.yes)
        elif command == "recover-identity":
            profile.recover_identity(args.adopt_current_volume)
        else:
            getattr(profile, command)()
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        print("Error:", error, file=sys.stderr)
        if args.command == "launch":
            show_account2_launch_error(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
