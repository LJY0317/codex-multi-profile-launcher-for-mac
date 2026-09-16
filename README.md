# Codex Multi-Profile Launcher for Mac

Run a second, isolated ChatGPT/Codex desktop profile on macOS without modifying or copying the official application.

The launcher starts `/Applications/ChatGPT.app` with a separate `CODEX_HOME` and Electron/Chromium user-data directory. The official app remains the first profile, while `ChatGPT (2).app` provides a clean second profile with its own login.
Both profiles execute the same protected `/Applications/ChatGPT.app` binary: only their profile state is separate, so updating the official app once updates the application binary used by both profiles on their next launch.

When both profiles must remain independently launchable, install the optional default-profile entry point with `scripts/install.sh install-default`. It creates `~/Applications/ChatGPT (1).app` with a distinct LaunchServices identifier and does not copy or modify the protected default profile. Pin that wrapper in the Dock in place of `/Applications/ChatGPT.app`; otherwise Dock clicks still target the official single bundle and cannot select a profile. The wrapper reuses only an exact default-profile process and refuses to start a duplicate when one is already running.

> [!IMPORTANT]
> This is an unofficial community project. It is not affiliated with, endorsed by, or supported by OpenAI. ChatGPT and Codex are trademarks of OpenAI.

[한국어 문서](docs/README.ko.md)

## What it creates

| Purpose | Path |
| --- | --- |
| Dock-friendly launcher | `~/Applications/ChatGPT (2).app` |
| Second Codex home | `~/.codex-account2` |
| Second desktop profile | `~/Library/Application Support/Codex-Account2` |
| Install manifest | `~/Library/Application Support/CodexMultiProfileLauncher/install-manifest.json` |

The installer never reads, copies, moves, or deletes the default profile's authentication data. It does not modify, clone, or re-sign `/Applications/ChatGPT.app`.

## Requirements

- macOS on Apple Silicon or Intel
- The official app at `/Applications/ChatGPT.app`
- Python 3 available as `python3`

This project has been tested with the current official macOS app available to the maintainer. OpenAI does not document this launcher pattern as a supported multi-account feature, so a future app update may require changes.

## Install

Review the scripts, then run:

```sh
./scripts/install.sh
open "$HOME/Applications/ChatGPT (2).app"
```

Sign in to the second window with the second account. Do not copy `auth.json`, cookies, or an existing profile into the new directories.

Check the installation at any time:

```sh
./scripts/status.sh
```

Older schema-1 installs recorded the kernel device number (`st_dev`), which can
change across macOS boots. Inspect a legacy install without changing it:

```sh
./scripts/recover-identity.sh
```

If the recorded inodes still match, all paths pass the ownership/symlink
checks, and they are currently on one APFS volume, recovery can be applied
explicitly with `./scripts/recover-identity.sh --adopt-current-volume`. The old
manifest is backed up before the atomic schema update. Because schema 1 did not
record a volume UUID, this explicit recovery does not claim that the old and
current volume UUIDs were proven identical.

You can also launch it from a terminal:

```sh
./scripts/launch.sh
```

## Uninstall and rollback

Quit the second profile first. Preview the exact removal set:

```sh
./scripts/uninstall.sh
```

Remove the launcher and all second-profile data, including its login and local conversations:

```sh
./scripts/uninstall.sh --yes
```

The uninstaller accepts only fixed paths recorded in the install manifest. It rejects symlinked paths, replaced directories, protected default-profile paths, mounted subtrees, and removal while the second profile is running.

The source checkout is intentionally left in place. Remove it separately if you no longer want the project. Remove a manually pinned Dock item from the Dock yourself.

## Isolation and limitations

The launcher separates these two storage boundaries:

- `CODEX_HOME`, which contains Codex configuration and local work state
- Electron/Chromium user data, including the desktop login session

It does not promise complete operating-system isolation. Keychain entries, URL handlers, permissions, caches, update services, and helper processes may still be shared or managed by the official application. Use Computer Use in one profile at a time until parallel use has been proven safe in your environment. Pair Remote separately in each account.

Do not point both profiles at the same `CODEX_HOME` or user-data directory. Do not use symlinks to share those directories. If you need to continue work across accounts, share the project files and a handoff document, preferably using separate Git worktrees for simultaneous work.

The installed wrapper looks for `python3` in the standard Homebrew and system command paths. If Python 3 is removed, reinstall it or run a current Python 3 interpreter against `src/codex_profile.py launch`.

## Safety design

- Fixed allowlist for every managed path
- Explicit protected paths for the official app and default profile
- Empty second profile; no credential migration code
- Per-directory APFS Volume UUID + inode identities recorded in the manifest
- The UUID is the APFS volume's `VolumeUUID` (not the transient `/dev/disk*`
  identifier, APFS container UUID, or physical-store identifier)
- Legacy device/inode manifests require explicit recovery; lookup failures never
  fall back to device-only or inode-only acceptance
- Dry-run uninstall by default
- No background service, login item, updater, or telemetry
- Official app core-file fingerprints recorded for status diagnostics

## Development

Run the checks on macOS:

```sh
python3 -m unittest discover -s tests -v
for script in scripts/*.sh; do sh -n "$script"; done
python3 -m py_compile src/codex_profile.py tests/test_safety.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for change guidelines and [SECURITY.md](SECURITY.md) for reporting security issues.

## Prior art

The launcher pattern was independently implemented after reviewing these community projects:

- [tbhrc/codex-multi-profile-launcher](https://github.com/tbhrc/codex-multi-profile-launcher): separate `CODEX_HOME`, user-data directory, and macOS wrapper pattern (MIT)
- [JqyModi/codex-multi-launcher](https://github.com/JqyModi/codex-multi-launcher): product and history-migration ideas; no source code copied

No source code from either project is included here.

## License

[MIT](LICENSE)
