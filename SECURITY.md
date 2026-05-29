# Security Policy

## Supported Versions

Only the latest `main` branch is supported with security updates. Pinned releases (v1.0.0, etc.) are best-effort.

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

To report a vulnerability, please use one of these channels:

1. **Preferred — GitHub Security Advisory**: https://github.com/amirpiccardodev-maker/vega/security/advisories/new (privato, gestito da GitHub)
2. **Email**: contatta tramite il profilo GitHub `amirpiccardodev-maker`

Include in your report:

- Type of vulnerability (e.g. prompt injection, ACL bypass, secret exfiltration, RCE)
- Component affected (e.g. `brain.py`, `tools/web.py`, `auth.py`)
- Steps to reproduce
- Impact (what an attacker could achieve)
- Suggested remediation (if any)

## Response timeline

- **24h**: acknowledgment that the report was received
- **7 days**: initial triage and severity classification (per CVSS 3.1)
- **30 days**: fix planned or workaround documented for high/critical
- **90 days**: full coordinated disclosure if not fixed earlier

## Scope

### In scope
- Authentication and authorization bypass
- Prompt injection / jailbreak techniques bypassing `prompt_shield`
- Tool ACL bypass (`tool_acl.py`)
- Secrets exfiltration via LLM output (bypass of `output_filter.py`)
- Path traversal in file tools (bypass of `path_guard.py`)
- WebSocket replay or injection
- DPO / CISO agent veto bypass

### Out of scope
- Issues in third-party dependencies — please report directly to upstream
- Attacks requiring physical access to the user's machine
- Social engineering against the user

## Threat model

VEGA is **self-hosted single-user**. The threat model assumes:

- The user owns and trusts their machine
- Attackers may attempt:
  - Network access from LAN (mitigated by Bearer auth + PIN)
  - Prompt injection via web/email content (mitigated by `prompt_shield`)
  - Data exfiltration via LLM tool calls (mitigated by `net_guard` + `output_filter`)
  - Manipulation through fake instructions in tool results (mitigated by `prompt_shield.sanitize`)

## Hall of Fame

Contributors who responsibly disclose security vulnerabilities will be credited here (with their permission) in the next release notes.

---

Thank you for helping keep VEGA and its users safe.
