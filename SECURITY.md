# Security Policy

## Reporting a vulnerability

Do not open a public issue containing credentials, cookies, conversation content, private file paths, or other sensitive data.

If the repository has private security reporting enabled, use GitHub's **Report a vulnerability** form. Otherwise, open a public issue containing only a redacted description and ask the maintainer for a private reporting channel.

Include the macOS version, ChatGPT app version, launcher revision, reproduction steps, and sanitized diagnostics. Never attach `auth.json`, profile databases, cookies, or a complete process environment.

## Security boundary

This launcher isolates `CODEX_HOME` and Electron/Chromium user data. It is not a sandbox and does not claim to isolate Keychain, macOS permissions, URL handlers, helper processes, or OpenAI account-side data.

The uninstaller is deliberately conservative. If a managed directory was replaced, moved across filesystems, symlinked, or contains a mounted subtree, it refuses removal and leaves manual review to the user.

Only install releases or source you have reviewed. The project does not provide an updater or download executable code at runtime.
