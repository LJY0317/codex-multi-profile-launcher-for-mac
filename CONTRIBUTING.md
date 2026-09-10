# Contributing

Contributions that keep the launcher small, auditable, macOS-focused, and easy to remove are welcome.

## Principles

- Never modify, clone, re-sign, or bundle the official ChatGPT application.
- Never read, print, copy, migrate, or delete authentication material from an existing profile.
- Keep the second profile empty on first launch.
- Keep every uninstall target on a fixed allowlist and protect the default profile paths in code.
- Avoid background services, login items, telemetry, and network dependencies.
- Preserve failure-safe behavior when the official app changes.

## Development

Use a temporary home directory in tests. Do not point tests at real Codex or ChatGPT data.

Before opening a pull request, run:

```sh
python3 -m unittest discover -s tests -v
for script in scripts/*.sh; do sh -n "$script"; done
python3 -m py_compile src/codex_profile.py tests/test_safety.py
```

Describe the macOS and ChatGPT app versions used for manual testing. Redact usernames, account data, credentials, cookies, local conversations, and private paths from logs and screenshots.
