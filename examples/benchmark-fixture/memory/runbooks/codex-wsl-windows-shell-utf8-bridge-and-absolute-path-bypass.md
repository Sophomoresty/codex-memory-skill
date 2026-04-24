---
doc_id: runbook-codex-wsl-windows-shell-utf8-bridge-and-absolute-path-bypass
doc_type: runbook
title: Codex WSL Windows shell UTF-8 bridge and absolute path bypass
status: active
scope: repo
tags: [wsl, windows, pwsh, shell]
triggers:
  - pwsh $_.LocalPort 被 zsh 改坏, 0.LocalPort is not recognized
keywords:
  - pwsh $_.LocalPort
  - zsh expansion
  - 0.LocalPort is not recognized
aliases:
  - pwsh $_.LocalPort 被 zsh 改坏, 0.LocalPort is not recognized
canonical: true
related: []
supersedes: []
last_verified: 2026-04-24
confidence: high
update_policy: merge
when_to_read:
  - before calling PowerShell from WSL with dollar expressions
---

# Codex WSL Windows shell UTF-8 bridge and absolute path bypass

Use the Windows shell bridge rules to avoid zsh mangling PowerShell dollar expressions such as `$_`.
