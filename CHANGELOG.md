# Changelog

Tutte le modifiche significative sono documentate qui. Formato basato su [Keep a Changelog](https://keepachangelog.com/) + [SemVer](https://semver.org).

## [1.0.0] — 2026-05-28 — Initial public release

**Sintesi**: 8 layer architetturali completi, 31 agenti specialisti, 18 fix di sicurezza enterprise allineati GDPR + NIS2, documentazione completa, OSS ready.

### Added

#### 🎙 Layer 1 — Voice & Audio
- Whisper STT base con beam_size=5, initial_prompt italiano, VAD filter
- Edge-TTS + ElevenLabs (opzionale), cache disco
- Wake word `hey_vega` + Whisper fallback frasi italiane
- Voice biometrics (resemblyzer) per multi-user
- Voice interrupt opt-in con cuffie
- Ascolto continuo (60s buffer)
- Sincronia voce + testo client-side

#### 🧠 Layer 2 — Brain & Reasoning
- Claude Sonnet 4.5 main + Haiku 4.5 routing/codegen
- Ollama local fallback (opt-in, smalltalk gratis)
- Prompt caching 2-livelli (static system + dynamic facts)
- Extended thinking adattivo (2K/5K/10K/15K budget)
- Multi-agent debate (3 voci parallele)
- Agent Fabric Planner/Executor/Verifier
- Long-horizon autonomous loop
- Summary intelligente token-based
- Cost tracking per-caller SQLite
- Batch API helper (50% sconto)

#### 💾 Layer 3 — Memory & Knowledge
- memory_graph SQLite + embeddings multilingual
- Mem0 episodic con LLM extraction
- news_graph RSS daily ingestion
- RAG docs auto-injection
- Honeypot canary 3 strings
- Freshness boost + importance decay
- Cluster by entity
- Multi-tenant via tenant_id
- Dedup cross-system weekly

#### 🔧 Layer 4 — Tool Ecosystem
- 124+ tool registered
- Tool ACL (HIGH/MEDIUM/LOW risk)
- Tool cache versioned LRU 5min
- Tool health auto-disable
- Tool chaining hints
- Prompt shield 5 categories injection
- Path guard traversal protection
- Progress feedback per tool >1.5s

#### 🏛 Layer 5 — Team Agentico (31 agenti)
- **Tier 0 Governance**: Steward (orchestrator), Architect (codegen agenti)
- **Tier 1 Compliance**: DPO (GDPR), CISO (NIS2), RSPP (D.Lgs 81), Audit Watcher
- **Tier 2 Operations** (16): Admin (fisco IT), Sales (mini-CRM), Email Manager, Report Builder, Client Onboarding (8-step), HR, Training Manager, File Organizer, Knowledge Mgmt, Bug Hunter, Innovator, Marketing, AI Expert, + 4 core
- **Tier 3 Intelligence** (5): Privacy/Cyber/Market/Compliance/Safety Scout
- **Monitor agents** (7): brain, memory, voice, security, network, task, health
- Hierarchy esplicita con `delegate()` API
- Steward orchestrator con classify + delegate vera + collect
- Architect scaffold-based codegen + AST validation + smoke test + hot-reload
- Template `consulting_smb` con 12 agenti operativi
- Workflow runner (3 pipeline: new_client_onboarding, month_close, project_close)

#### 🛡 Layer 6 — Security (18 layer enterprise)
- Bearer token + PIN auth con rate limit + lockout
- TLS self-signed opt-in
- CORS allowlist
- CSP strict + XSS hardening
- Prompt shield 5 categorie
- Tool ACL multi-tier
- Net guard outbound allowlist + logging
- Audit log hash-chained tamper-evident
- CVE scanner pip-audit weekly
- WS replay protection
- .env vault AES-256 PBKDF2
- Output filter (mask IBAN/CF/JWT/CC Luhn)
- Path guard
- Honeypot canary leak detection
- DPO/CISO/RSPP agent governance

#### 🎨 Layer 7 — UI/UX & PWA
- UI liquida generativa: orb WebGL che respira + palette periwinkle/indigo VEGA (fallback canvas 2D)
- Automation Mode v2 con 4 tab (org chart / detail / chat / overview)
- Operations Center 5 tab (health / workflow / queue / log / trace)
- Morning Briefing auto-card
- Onboarding wizard 5-step
- Tutorial 5 tab
- Theme toggle dark/light/auto
- PWA installable + service worker + Web Push
- Mobile polish (safe-area iOS, tap ≥44px)
- Accessibility (focus rings, skip link, prefers-contrast/reduced-motion)
- Card history storico sessione
- Drag & drop file analysis

#### 🏗 Layer 8 — Infrastruttura
- Event bus in-process pub/sub + JSONL persistence
- Task queue SQLite WAL + workers + retry + DLQ
- Workflow engine JSON DSL + Workflow runner
- Automation cron scheduler
- Distributed tracing (trace_id propagation)
- Telemetry SQLite 30gg retention
- Health endpoint /api/health{,/live,/ready}
- Hot-reload UI watch
- SQLite hardening (WAL + busy_timeout + synchronous=NORMAL + temp_store=MEMORY)
- Shared embedder singleton

### Documentation
- README.md professionale con badges + quick start
- ARCHITECTURE.md con 8 ADR
- GUIDA_UTENTE.md (Italian user guide)
- CHEAT_SHEET.md (1-page A4 printable)
- VIDEO_SCRIPTS.md (6 walkthrough scripts)
- CONTRIBUTING.md
- LICENSE (MIT)
- Comprehensive .gitignore (protect local data)

### Testing
- 46 tests in `tests/full_system_test.py` (45/46 PASS)
- Red team security tests in `tests/security_redteam.py` (36/36 PASS)

### Internationalization
- Italian-first (UI, voice, agents personas, documentation)
- English in code comments + commit messages

---

[1.0.0]: https://github.com/amirpiccardodev-maker/vega/releases/tag/v1.0.0
