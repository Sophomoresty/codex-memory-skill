---
doc_id: runbook-windows-toolchain-paths-and-wsl-call-baseline
doc_type: runbook
title: Windows toolchain paths and WSL call baseline
status: active
scope: repo
tags: [windows, wsl, shell, pwsh, path]
triggers:
  - WSL 调 Windows shell 或 PowerShell
keywords:
  - WSL
  - Windows shell
  - PowerShell
  - pwsh
  - path baseline
aliases:
  - windows toolchain paths
  - WSL call baseline
  - Windows shell from WSL
  - PowerShell path baseline
canonical: true
related: []
supersedes: []
last_verified: 2026-04-24
confidence: high
update_policy: merge
when_to_read:
  - before calling Windows shell, pwsh, or PowerShell from WSL
---

# Windows toolchain paths and WSL call baseline

## Trigger

- Use this note when a WSL command calls Windows shell or PowerShell.
- Use this note for general Windows shell path and wrapper decisions from WSL.

## Preconditions

- Prefer `cmd.exe`, `powershell.exe`, or `pwsh.exe` through PATH.
- Do not call Windows shell binaries through hard-coded `/mnt/c/...` paths.

## Steps

1. Wrap literal PowerShell snippets in single quotes at the outer zsh layer when possible.
2. Escape `$` when double quotes are required.
3. Keep reusable Windows shell wrappers in a stable local scripts path instead of a temporary directory.

## Verification

- Re-run the exact WSL command and confirm PowerShell receives expressions such as `$_` unchanged.
- Confirm PATH resolves the expected Windows shell command.
