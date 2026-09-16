# Repository instructions

- Treat `/Applications/ChatGPT.app`, `~/.codex`, and `~/Library/Application Support/Codex` as protected read-only paths.
- Never read, print, copy, migrate, or delete authentication files, cookies, profile databases, or conversation content from a real profile.
- Keep all uninstall targets on the fixed allowlist and require manifest validation before removal.
- Use temporary fake home directories for tests. Tests must never point at a real ChatGPT or Codex profile.
- Keep the project macOS-only, dependency-light, auditable, and easy to remove.
- Run the safety tests, shell syntax checks, and Python compilation checks after changes.

## Multi-profile architecture

- `/Applications/ChatGPT.app` is the single protected official ChatGPT binary. Do not clone, patch, re-sign, or maintain per-account copies of it.
- `ChatGPT (1).app` and `ChatGPT (2).app` are lightweight profile selectors that execute the same official app with separate profile state. Updating the official app once therefore updates the application binary used by both profiles on their next launch.
- Keep profile state isolated. Do not share or copy `CODEX_HOME`, Electron/Chromium user-data, authentication files, cookies, profile databases, or conversation data between accounts.
- Keep wrappers thin and removable. This repository owns ChatGPT profile launch/isolation and its optional menu integration; do not absorb unrelated bridge/runtime/service implementations into it.
