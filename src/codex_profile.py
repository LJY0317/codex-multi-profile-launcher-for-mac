#!/usr/bin/env python3
"""Manage one fixed, empty alternate ChatGPT/Codex profile on macOS."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import shutil
import subprocess
import sys


IDENTIFIER = "local.codex-multi-profile-launcher.account2"
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
        temporary = self.meta / "manifest.tmp"
        with temporary.open("x") as file:
            json.dump(manifest, file, indent=2)
            file.write("\n")
        os.replace(temporary, self.manifest)

    def load(self):
        self.safe(self.meta)
        if self.manifest.is_symlink():
            raise RuntimeError("Symlink manifest refused")
        manifest = json.loads(self.manifest.read_text())
        if manifest.get("schema") != 1 or manifest.get("id") != IDENTIFIER:
            raise RuntimeError("Unknown manifest")
        if manifest.get("meta_identity") != identity(self.meta):
            raise RuntimeError("Metadata directory identity changed")
        seen = set()
        for entry in manifest["created"]:
            path = Path(entry["path"])
            self.safe(path)
            if path not in self.paths or str(path) in seen:
                raise RuntimeError("Invalid or duplicate manifest entry")
            seen.add(str(path))
            if path.exists() and identity(path) != entry["identity"]:
                raise RuntimeError("Directory replaced; preserving: " + str(path))
        return manifest

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
            "schema": 1,
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


def identity(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


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
        "command", choices=["install", "launch", "status", "uninstall"]
    )
    parser.add_argument(
        "--yes", action="store_true", help="Apply uninstall; default is dry run"
    )
    args = parser.parse_args()
    profile = Profile()
    try:
        if args.command == "uninstall":
            profile.uninstall(args.yes)
        else:
            getattr(profile, args.command)()
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        print("Error:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
