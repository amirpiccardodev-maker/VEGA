<div align="center">

# ✦ V.E.G.A.

> **Voice. Eyes. Guidance. Agency.**
> *L'assistente che orbita intorno a te.*

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

**🇮🇹 Italiano** · [🇬🇧 English](README.en.md)

</div>

---

## Cos'è

Vega è un **assistente AI personale completo** che gira sul tuo PC. Niente cloud (eccetto le chiamate API ad Anthropic, già cifrate HTTPS). Niente dati che escono se non quelli necessari per generare le risposte.

Ha **31 agenti specialisti virtuali** organizzati come un'azienda vera (governance, compliance, operations, intelligence) con cui puoi parlare individualmente, **124+ tool** integrati (mail, calendar, web, vision, image gen, file ops…), **memoria multi-livello persistente**, **18 layer di sicurezza enterprise-grade** allineati GDPR + NIS2, e una **UI liquida generativa** (orb WebGL che respira e reagisce alla voce) con voce italiana.

---

## ✨ Highlight

| Capacità | Dettaglio |
|---|---|
| 🗣 **Voce italiana** | Whisper STT + Edge-TTS, wake word "Vega", interrupt vocale, ascolto continuo |
| 👀 **Vision** | Drag&drop immagini/PDF, screenshot analysis live |
| 🧠 **Modelli AI ruotati** | Sonnet 4.5 (main) + Haiku 4.5 (routing/agents) + Ollama locale (fallback gratis) |
| 💾 **Memoria multi-livello** | Mem0 episodic + memory_graph SQLite + RAG docs + news_graph + canary |
| 🏛 **31 agenti specializzati** | DPO, CISO, RSPP, Admin, Sales, Email, Report Builder, Scout daily… |
| 🔄 **Workflow pipeline** | 3 workflow consulting pre-fatti (onboarding, month_close, project_close) |
| 🏗 **Architect generativo** | Crea nuovi agenti da discovery interview (AST validation + smoke test + hot-reload) |
| 🛡 **Sicurezza enterprise** | Auth Bearer + PIN, TLS opt-in, CORS, CSP, prompt shield, tool ACL, audit hash-chained, honeypot, CVE scanner |
| 📱 **PWA installabile** | Accesso LAN da mobile, push notifications, mic background |
| 💰 **Costo ridotto** | Prompt caching 2 livelli, batch API, Ollama fallback → ~$1-3/mese uso quotidiano |

---

## 🚀 Quick Start

### Requisiti
- Windows 10/11 (può girare anche Linux/Mac con piccoli adatt.)
- Python 3.14+
- ~2GB disco libero (modelli ML)
- Microfono (per voce)
- API key Anthropic ([console.anthropic.com](https://console.anthropic.com))

### Installazione
```bash
git clone https://github.com/amirpiccardodev-maker/VEGA.git
cd VEGA
setup.bat              # Windows: crea venv + installa deps
```

### Configurazione
1. Copia `.env.example` in `.env`
2. Aggiungi la tua `ANTHROPIC_API_KEY`
3. Opzionale: `GMAIL_APP_PASSWORD` per accesso email

### Avvio
```bash
# Modalità silent (consigliata):
Vega.vbs

# Modalità debug:
Vega.bat
```

Il browser si apre automaticamente. Al primo avvio appare un wizard di onboarding.

### Primo uso
1. Wizard ti chiede: PIN (opzionale), città (per meteo), team mode (sblocca 31 agenti)
2. Premi il microfono e di' **"Vega"**
3. Aspetta il bip → fai domanda
4. Esplora i bottoni topbar (❓ guida, 🏛 agenti, 🛠 ops center)

---

## 🧭 Architettura — 8 layer

```
┌─────────────────────────────────────────────────────────┐
│ 7  UI/UX & PWA       — HUD HTML/JS, Automation Mode,    │
│                        mobile, theme dark/light/auto    │
├─────────────────────────────────────────────────────────┤
│ 5  Team Agentico     — Steward, DPO, CISO, RSPP,        │
│                        Architect, 12 consulting, 7 mon. │
│ 4  Tool Ecosystem    — 124+ tool, ACL, cache, chaining  │
│ 2  Brain & Reasoning — Sonnet+Haiku+Ollama, debate,     │
│                        agent_fabric, long_horizon       │
│ 1  Voice & Audio     — Whisper, Edge-TTS, wake word,    │
│                        voice interrupt, voice biometrics │
├─────────────────────────────────────────────────────────┤
│ 3  Memoria           — Mem0 + memory_graph + RAG +      │
│                        news_graph + cluster + decay     │
│ 8  Infrastruttura    — Bus, task_queue, workflow,       │
│                        scheduler, tracing, health       │
│ 6  Sicurezza         — 18 layer enterprise (GDPR/NIS2)  │
└─────────────────────────────────────────────────────────┘
```

Vedi [ARCHITECTURE.md](ARCHITECTURE.md) per dettagli.

---

## 🛡 Sicurezza & Compliance

Allineato a:
- **GDPR** (Reg. UE 2016/679) + provvedimenti Garante Privacy Italia
- **NIS2** (Dir UE 2022/2555, D.Lgs 138/2024) + ACN guidance
- **D.Lgs 81/2008** sicurezza sul lavoro
- **ISO 27001/27002** controlli di sicurezza

18 layer attivi: Bearer + PIN, TLS, CORS allowlist, CSP, prompt shield, tool ACL, output filter (mask IBAN/CF/JWT), path guard, net guard, audit log hash-chained, rate limit + lockout, honeypot canary, CVE scanner, WS replay, .env vault, mic kill switch, privacy mode, DPO/CISO/RSPP agents.

> ⚠️ **Disclaimer**: gli agenti DPO/CISO/RSPP sono **assistenti operativi**, non sostituiscono i ruoli formali richiesti dalla normativa. La responsabilità legale resta al Titolare del trattamento.

---

## 🏛 Il team di 31 agenti

| Tier | Agente | Ruolo |
|---|---|---|
| 0 | 🧭 Steward | Orchestratore richieste |
| 0 | 🏗 Architect | Genera nuovi agenti |
| 1 | 🔐 DPO | GDPR Art. 5/6/25/30/32/33/35 |
| 1 | 🛡 CISO | NIS2 incident response |
| 1 | 🦺 RSPP | D.Lgs 81/08 sicurezza lavoro |
| 1 | 📋 Audit Watcher | Hash chain integrity |
| 2 | 💰 Admin | Fatturazione + scadenze fiscali italiane |
| 2 | 💼 Sales | Mini-CRM lead pipeline |
| 2 | 📧 Email Manager | Smistamento + draft replies |
| 2 | 📑 Report Builder | Report cliente weekly/monthly |
| 2 | 🏢 Client Onboarding | Checklist 8-step |
| 2 | 👥 HR | Ferie, contratti, review |
| 2 | 🎓 Training Manager | Formazione obbligatoria |
| 2 | 📁 File Organizer | Cartelle clienti + archive |
| 2 | 📚 Knowledge Mgmt | SOP, post-mortem |
| 2 | 🐛 Bug Hunter | Health check + propose-diff |
| 2 | 💡 Innovator | Weekly proposals |
| 2 | 📢 Marketing | Brand strategy |
| 2 | 🧠 AI Expert | Model routing advisor |
| 3 | 📜 Privacy Scout | Daily Garante + Federprivacy + EDPB |
| 3 | 🛡 Cyber Scout | Daily CSIRT + CISA + ENISA + ACN |
| 3 | 📈 Market Scout | Trend tech/business |
| 3 | 🏛 Compliance Scout | Agenzia Entrate, INPS, INAIL |
| 3 | 🦺 Safety Scout | Ispettorato Lavoro + INAIL safety |
| 4 | 7 Monitor agents | Brain, Memory, Voice, Security, Network, Task, Health |

---

## 📁 Struttura repo (top-level)

```
vega/
├── server.py             Flask + WebSocket main server
├── brain.py              Anthropic Claude integration
├── engine.py             Voice/STT/TTS pipeline
├── memory_graph.py       Memory SQLite + embeddings
├── episodic_memory.py    Mem0 integration
├── tools/                124+ tool modules
├── agents/               31 agent modules
│   ├── team_base.py      BaseAgent class
│   ├── team_registry.py  Dynamic loader
│   ├── dpo.py, ciso.py, rspp.py, ...
│   ├── monitor_*.py      7 monitor agents
│   └── _pending/         Architect staging
├── data/                 LOCAL data (gitignored)
│   ├── gdpr_register.json
│   ├── incidents/
│   ├── compliance_reports/
│   ├── agent_templates/
│   ├── blueprints/
│   ├── client_files/
│   └── ...
├── ui/                   HTML/CSS/JS frontend (PWA)
├── tests/                full_system_test.py + security_redteam.py
└── docs/                 GUIDA_UTENTE.md, CHEAT_SHEET.md, VIDEO_SCRIPTS.md
```

---

## 🧪 Test

```bash
venv/Scripts/python.exe tests/full_system_test.py
venv/Scripts/python.exe tests/security_redteam.py
```

---

## 💸 Costi stimati

- Uso quotidiano ~50 query/giorno: **~$1-3/mese**
- Con Ollama locale per smalltalk: **~$0.50-1.50/mese**
- Architect deploy (one-time): ~$0.10
- Cache hit rate target: >40% → dimezza i costi input

Vedi `/api/metrics/costs` per il tuo breakdown reale.

---

## 🤝 Contributing

Benvenute PR. Vedi [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT. Vedi [LICENSE](LICENSE).

---

## 🙏 Crediti

- [Anthropic Claude](https://www.anthropic.com) — il cervello
- [OpenAI Whisper](https://github.com/openai/whisper) — STT
- [Microsoft Edge-TTS](https://github.com/rany2/edge-tts) — voce
- [Mem0](https://mem0.ai) — episodic memory
- [Sentence Transformers](https://www.sbert.net) — embeddings
- [Pollinations.ai](https://pollinations.ai) — image gen
- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake detection

---

<div align="center">

**Costruito con onestà brutale e troppe ore di sonno perse.**

[Guida utente](GUIDA_UTENTE.md) · [Cheat sheet](CHEAT_SHEET.md) · [Architettura](ARCHITECTURE.md) · [Video scripts](VIDEO_SCRIPTS.md)

</div>
