# VEGA Roadmap

What we're working on, what's planned, what we explicitly will NOT do. This is **not a promise** — it's a working document.

Last update: 2026-05

---

## ✦ Current focus (Q2 2026)

- [x] **v1.0.0** initial public release — 8 layers, 31 agents, MIT, OSS-ready
- [x] **Brand rename** Vega → VEGA
- [ ] **Liquid/Generative UI redesign** — WebGL sphere, breathing gradients, generative particles
- [ ] **README/docs bilingue** (IT + EN)
- [ ] **Topics + Release v1.0.0 tag** on GitHub
- [ ] **First demo video** (3 min walkthrough)
- [ ] **First batch of feedback** from real-world usage

## ✦ Near (Q3 2026)

- [ ] **Agent enrichment**: i 12 agenti consulting hanno scheletri robusti ma serve hardening operativo reale (uso quotidiano + fix bug emergenti)
- [ ] **Templates industry aggiuntivi**: legal_studio, ecommerce, healthcare, real_estate
- [ ] **Computer Use API** (Anthropic) come tool: VEGA controlla mouse/tastiera per scenari aperti
- [ ] **Vision streaming live** (webcam, non solo screenshot statici)
- [ ] **Mobile-first companion app** (Flutter o Capacitor)
- [ ] **Workflow builder visuale** nel browser (no più solo JSON)
- [ ] **Backup E2E cifrato** (Age/rage) su S3/B2 opt-in
- [ ] **Documentation site** su GitHub Pages

## ✦ Future / exploratory

- [ ] **Voice cloning locale** via XTTS (no più ElevenLabs cloud)
- [ ] **Multi-tenant deep** (1 utente = 1 namespace completo)
- [ ] **Federated multi-device sync** (CRDT + Age E2E)
- [ ] **Claude Agent SDK migration** — sostituire `agent_fabric` custom con SDK ufficiale
- [ ] **Anthropic Managed Agents** integration quando GA
- [ ] **Open Interpreter as fallback tool** per scenari completamente open-ended
- [ ] **VEGA Hub** — server pubblico che indicizza skills/agents/templates contribuiti dalla community
- [ ] **Plugin marketplace** con firma + sandbox

## ✦ NON-goals (cose che NON faremo)

Per chiarezza, queste cose sono **fuori scope**:

- ❌ **Smart home / Matter / HomeKit** — VEGA non è un controller domotico. Usa Home Assistant per quello.
- ❌ **Cloud-only versione** — VEGA è self-hosted-first per design. Niente versione SaaS dove i tuoi dati vivono sui nostri server.
- ❌ **Mobile app nativa standalone** — vogliamo PWA + companion app, non un secondo prodotto da mantenere.
- ❌ **Sostituzione del DPO / CISO umano** — VEGA li affianca, NON li sostituisce legalmente.
- ❌ **Trading automatico / esecuzione finanziaria** — categorizza, suggerisce, mai esegue.
- ❌ **Compagnia AI emotiva** — VEGA è uno strumento di produttività, non un amico virtuale.

## ✦ Decisioni di design recenti (ADR-style)

Vedi [ARCHITECTURE.md § "Decisioni di design"](ARCHITECTURE.md) per il razionale completo.

## ✦ Come influenzare la roadmap

Apri un **Feature Request** in [Issues](https://github.com/amirpiccardodev-maker/vega/issues) con il template apposito. Includi:

1. Quale problema risolve
2. Quale layer dell'architettura tocca
3. Sei disposto a contribuire al codice?

PR ben fatte hanno priorità su feature request senza commit.
