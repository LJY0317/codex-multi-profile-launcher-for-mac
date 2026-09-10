# Repository instructions

- Treat `/Applications/ChatGPT.app`, `~/.codex`, and `~/Library/Application Support/Codex` as protected read-only paths.
- Never read, print, copy, migrate, or delete authentication files, cookies, profile databases, or conversation content from a real profile.
- Keep all uninstall targets on the fixed allowlist and require manifest validation before removal.
- Use temporary fake home directories for tests. Tests must never point at a real ChatGPT or Codex profile.
- Keep the project macOS-only, dependency-light, auditable, and easy to remove.
- Run the safety tests, shell syntax checks, and Python compilation checks after changes.
