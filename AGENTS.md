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
- Keep wrappers thin and removable. This repository owns ChatGPT profile launch/isolation only; Codex Web GPT bridge/runtime/menu integrations belong to the bridge repository, not here.

## Official ChatGPT reference

- Treat OpenAI's current **ChatGPT desktop app** (the **ChatGPT macOS app** in macOS-specific OpenAI documentation) as the compatibility reference for launch and profile behavior. Inspect `/Applications/ChatGPT.app` read-only when a wrapper assumption needs revalidation.
- Prefer documented OpenAI behavior and the public `openai/codex` contract where relevant. Do not copy, patch, or reverse-engineer private application internals, authentication state, minified code, or DOM behavior into this launcher.
- Keep local behavior limited to profile selection/isolation that the official app demonstrably accepts. If a future official app supports the required multi-profile behavior directly, remove the redundant wrapper behavior instead of preserving a parallel local implementation.

## MacLagMonitor for performance investigations

When a future task concerns lag, fan noise, CPU/memory use, or local performance
optimization, first consult `~/LJY Projects/MacLagMonitor/AGENTS.md` and its
existing runtime records under
`~/Library/Application Support/MacLagMonitor/data/`. Read only the relevant
time window in `summary.tsv`, `process-context.tsv`, and `incidents/`; do not
run a full historical scan or trigger new collection for routine maintenance.

Correlate timestamps and same-snapshot process ancestry with this project's
request/build records. Separate application, child-command, build/package,
browser, and WindowServer load; a busy process alone does not establish the
cause of fan noise. Compare like-for-like idle, active, and post-task periods
when measuring a proposed optimization. Treat missing samples as unknown, and
do not interpret `memory_pressure` free percentage as Activity Monitor's
memory-pressure graph or a GPU helper's CPU usage as GPU utilization.

MacLagMonitor is an optional read-only diagnostic reference, not a runtime or
build dependency. Preserve its configuration, process, and existing changes.
Do not add continuous profiling, restart services, or change system settings
just to gather evidence. Keep raw diagnostics and machine-specific results
local; do not copy them into public documentation or commits.
