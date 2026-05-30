<div align="center">

# ✦ V.E.G.A.

> **Voice. Eyes. Guidance. Agency.**
> *The assistant that orbits around you.*

Self-hosted personal AI assistant — Italian-first, privacy-first, with a 31-agent team organized in 5 hierarchical tiers. Inspired by the brightest star of the Lyra constellation.

[![License: MIT](https://img.shields.io/github/license/amirpiccardodev-maker/vega?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14+-blue?style=flat-square&logo=python)](https://www.python.org)
[![Claude](https://img.shields.io/badge/Powered_by-Anthropic_Claude_4.5-7c3aed?style=flat-square)](https://www.anthropic.com)
[![GDPR](https://img.shields.io/badge/GDPR-compliant_by_design-success?style=flat-square)]()
[![NIS2](https://img.shields.io/badge/NIS2-aligned-success?style=flat-square)]()
[![Last commit](https://img.shields.io/github/last-commit/amirpiccardodev-maker/vega?style=flat-square)](https://github.com/amirpiccardodev-maker/vega/commits/main)
[![Stars](https://img.shields.io/github/stars/amirpiccardodev-maker/vega?style=flat-square)](https://github.com/amirpiccardodev-maker/vega/stargazers)
[![Issues](https://img.shields.io/github/issues/amirpiccardodev-maker/vega?style=flat-square)](https://github.com/amirpiccardodev-maker/vega/issues)
[![Repo size](https://img.shields.io/github/repo-size/amirpiccardodev-maker/vega?style=flat-square)](https://github.com/amirpiccardodev-maker/vega)

[🇮🇹 Italiano](README.md) · **🇬🇧 English**

</div>

---

## What it is

Vega is a **complete personal AI assistant** that runs on your own PC. No cloud (except the Anthropic API calls, already encrypted over HTTPS). No data leaves your machine beyond what's strictly needed to generate answers.

It has **31 virtual specialist agents** organized like a real company (governance, compliance, operations, intelligence) that you can talk to individually, **124+ integrated tools** (mail, calendar, web, vision, image gen, file ops…), **persistent multi-level memory**, **18 enterprise-grade security layers** aligned with GDPR + NIS2, and a **generative liquid UI** (a breathing, voice-reactive WebGL orb) with an Italian voice.

---

## ✨ Highlights

| Capability | Detail |
|---|---|
| 🗣 **Italian voice** | Whisper STT + Edge-TTS, "Vega" wake word, voice interrupt, continuous listening |
| 👀 **Vision** | Drag & drop images/PDF, live screenshot analysis |
| 🧠 **Tiered AI models** | Sonnet 4.5 (main) + Haiku 4.5 (routing/agents) + local Ollama (free fallback) |
| 💾 **Multi-level memory** | Mem0 episodic + memory_graph SQLite + RAG docs + news_graph + canary |
| 🏛 **31 specialized agents** | DPO, CISO, RSPP, Admin, Sales, Email, Report Builder, daily Scouts… |
| 🔄 **Workflow pipelines** | 3 prebuilt consulting workflows (onboarding, month_close, project_close) |
| 🏗 **Generative architect** | Creates new agents from a discovery interview (AST validation + smoke test + hot-reload) |
| 🛡 **Enterprise security** | Bearer + PIN auth, opt-in TLS, CORS, CSP, prompt shield, tool ACL, hash-chained audit, honeypot, CVE scanner |
| 📱 **Installable PWA** | LAN access from mobile, push notifications, background mic |
| 💰 **Low cost** | 2-level prompt caching, batch API, Ollama fallback → ~$1–3/month for daily use |

---

## 🚀 Quick Start

### Requirements
- Windows 10/11 (can also run on Linux/Mac with small tweaks)
- Python 3.14+
- ~2GB free disk (ML models)
- Microphone (for voice)
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### Install
```bash
git clone https://github.com/amirpiccardodev-maker/VEGA.git
cd VEGA
setup.bat              # Windows: creates venv + installs deps
```

### Configure
1. Copy `.env.example` to `.env`
2. Add your `ANTHROPIC_API_KEY`
3. Optional: `GMAIL_APP_PASSWORD` for email access

### Run
```bash
# Silent mode (recommended):
Vega.vbs

# Debug mode:
Vega.bat
```

The browser opens automatically. An onboarding wizard appears on first launch.

### First use
1. The wizard asks for: PIN (optional), city (for weather), team mode (unlocks 31 agents)
2. Press the microphone and say **"Vega"**
3. Wait for the beep → ask your question
4. Explore the topbar buttons (❓ help, 🏛 agents, 🛠 ops center)

---

## 🧭 Architecture — 8 layers

```
┌─────────────────────────────────────────────────────────┐
│ 7  UI/UX & PWA       — liquid orb UI, Automation Mode,  │
│                        mobile, theme dark/light/auto    │
├─────────────────────────────────────────────────────────┤
│ 5  Agent Team        — Steward, DPO, CISO, RSPP,        │
│                        Architect, 12 consulting, 7 mon. │
│ 4  Tool Ecosystem    — 124+ tools, ACL, cache, chaining │
│ 2  Brain & Reasoning — Sonnet+Haiku+Ollama, debate,     │
│                        agent_fabric, long_horizon       │
│ 1  Voice & Audio     — Whisper, Edge-TTS, wake word,    │
│                        voice interrupt, voice biometrics │
├─────────────────────────────────────────────────────────┤
│ 3  Memory            — Mem0 + memory_graph + RAG +      │
│                        news_graph + cluster + decay     │
│ 8  Infrastructure    — Bus, task_queue, workflow,       │
│                        scheduler, tracing, health       │
│ 6  Security          — 18 enterprise layers (GDPR/NIS2) │
└─────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

---

## 🛡 Security & Compliance

Aligned with:
- **GDPR** (EU Reg. 2016/679) + Italian Data Protection Authority guidance
- **NIS2** (EU Dir. 2022/2555, Italian Legislative Decree 138/2024) + ACN guidance
- **Italian Legislative Decree 81/2008** workplace safety
- **ISO 27001/27002** security controls

18 active layers: Bearer + PIN, TLS, CORS allowlist, CSP, prompt shield, tool ACL, output filter (masks IBAN/tax-ID/JWT), path guard, net guard, hash-chained audit log, rate limit + lockout, honeypot canary, CVE scanner, WS replay protection, .env vault, mic kill switch, privacy mode, DPO/CISO/RSPP agents.

> ⚠️ **Disclaimer**: the DPO/CISO/RSPP agents are **operational assistants**; they do not replace the formal roles required by law. Legal responsibility remains with the Data Controller.

---

## 🏛 The 31-agent team

| Tier | Agent | Role |
|---|---|---|
| 0 | 🧭 Steward | Request orchestrator |
| 0 | 🏗 Architect | Generates new agents |
| 1 | 🔐 DPO | GDPR Art. 5/6/25/30/32/33/35 |
| 1 | 🛡 CISO | NIS2 incident response |
| 1 | 🦺 RSPP | Italian L.D. 81/08 workplace safety |
| 1 | 📋 Audit Watcher | Hash chain integrity |
| 2 | 💰 Admin | Invoicing + Italian tax deadlines |
| 2 | 💼 Sales | Mini-CRM lead pipeline |
| 2 | 📧 Email Manager | Triage + draft replies |
| 2 | 📑 Report Builder | Weekly/monthly client reports |
| 2 | 🏢 Client Onboarding | 8-step checklist |
| 2 | 👥 HR | Leave, contracts, reviews |
| 2 | 🎓 Training Manager | Mandatory training |
| 2 | 📁 File Organizer | Client folders + archive |
| 2 | 📚 Knowledge Mgmt | SOPs, post-mortems |
| 2 | 🐛 Bug Hunter | Health check + propose-diff |
| 2 | 💡 Innovator | Weekly proposals |
| 2 | 📢 Marketing | Brand strategy |
| 2 | 🧠 AI Expert | Model routing advisor |
| 3 | 📜 Privacy Scout | Daily Garante + Federprivacy + EDPB |
| 3 | 🛡 Cyber Scout | Daily CSIRT + CISA + ENISA + ACN |
| 3 | 📈 Market Scout | Tech/business trends |
| 3 | 🏛 Compliance Scout | Italian Revenue Agency, INPS, INAIL |
| 3 | 🦺 Safety Scout | Labor Inspectorate + INAIL safety |
| 4 | 7 Monitor agents | Brain, Memory, Voice, Security, Network, Task, Health |

---

## 🧪 Tests

```bash
venv/Scripts/python.exe tests/full_system_test.py
venv/Scripts/python.exe tests/security_redteam.py
```

---

## 💸 Estimated cost

- Daily use ~50 queries/day: **~$1–3/month**
- With local Ollama for smalltalk: **~$0.50–1.50/month**
- Architect deploy (one-time): ~$0.10
- Cache hit-rate target: >40% → halves input cost

See `/api/metrics/costs` for your real breakdown.

---

## 🤝 Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT. See [LICENSE](LICENSE).

---

## 🙏 Credits

- [Anthropic Claude](https://www.anthropic.com) — the brain
- [OpenAI Whisper](https://github.com/openai/whisper) — STT
- [Microsoft Edge-TTS](https://github.com/rany2/edge-tts) — voice
- [Mem0](https://mem0.ai) — episodic memory
- [Sentence Transformers](https://www.sbert.net) — embeddings
- [Pollinations.ai](https://pollinations.ai) — image gen
- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake detection

---

<div align="center">

**Built with brutal honesty and too many lost hours of sleep.**

[User guide](GUIDA_UTENTE.md) · [Cheat sheet](CHEAT_SHEET.md) · [Architecture](ARCHITECTURE.md) · [Video scripts](VIDEO_SCRIPTS.md)

</div>
