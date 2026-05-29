# 🤖 V.E.G.A. — Guida per persone normali

Una guida pratica per usare Vega senza dover capire come è fatto dentro.

**Versione**: maggio 2026 · 8 layer · 31+ agenti · 124+ tool · ~150 feature

> ⚠️ **Onestà**: gli agenti hanno struttura completa ma non sono battle-tested. Per uso personale vanno bene; per consegnarli a terzi servirebbe 1 settimana di hardening.

---

## 🎯 In una frase

**Vega è il tuo assistente personale AI che vive sul tuo PC, ti capisce a voce e a tastiera, ha 31 esperti virtuali, e tutto resta locale** (a parte le chiamate AI ad Anthropic, già cifrate HTTPS).

---

## 🚀 Le 6 cose da provare per prime

1. **Apri Vega** → al primo avvio appare wizard "👋 BENVENUTO" → 5 step in 60 sec
2. **Parla**: di' **"Vega"** → aspetta il bip → fai domanda
3. **Scrivi** nella casella in basso (Invio per inviare)
4. **Trascina** un file/immagine/PDF dentro → Vega lo legge
5. **Apri 🏛 Automation Mode** → vedi i 31 agenti vivi
6. **Apri 🛠 Operations Center** → diagnosi sistema, workflow, log

---

## 📱 Bottoni topbar

| Icona | Cosa fa |
|---|---|
| ❓ | **Guida** 5 tab (voce / agenti / comandi / scorciatoie / privacy) |
| 🩺 | Diagnosi |
| 🖥 | Stato PC |
| 📊 | Statistiche uso + token + cache hit |
| 🏛 | **Automation Mode** (agenti + chat) |
| 💡 | Proposte Innovator |
| 🗂 | Storico card sessione |
| 🛠 | **Operations Center** (health + workflow + queue + log + trace) |
| ⚙ | Impostazioni |
| ⛶ | Schermo intero (F11) |

---

## 🗣 Frasi magiche

### Base
| Frase | Effetto |
|---|---|
| "Che ore sono" | Ora + data |
| "Che tempo fa" | Card meteo |
| "Leggimi le email" | Riassunto inbox |
| "Manda mail a Marco" | Bozza (chiede conferma) |
| "Genera immagine di X" | Pollinations.ai gratis |
| "Aggiungi todo: ..." | Salva in lista |
| "Imposta timer 10 minuti" | Timer attivo |
| "Apri Spotify" / "Word" | Lancia app |
| "Stop Vega" | Interrompe |

### Avanzate
| Frase | Effetto |
|---|---|
| "Guarda lo schermo" | Screenshot + analisi Claude |
| "Ricorda che ho un gatto Pepe" | Mem0 persistente |
| "Dimmi cosa sai su Marco" | Dossier entità clusterizzato |
| "Pensaci bene su X" | Extended thinking (qualità++ costo++) |
| "Dibattito su: devo cambiare lavoro?" | 3 voci + sintesi |
| "Agente: organizza la settimana" | Multi-step planner |
| "Missione: trova 5 case sotto 1500€" | Long-horizon autonomo |
| "Ultime news privacy" | Privacy Scout (cached) |

---

## 🏛 Automation Mode — i 31 agenti

### 2 tab in alto

**🏛 BOARD**: 31 tile divisi in 4 tier, click per pause/run/disable. Stream live messaggi a destra.

**💬 CHAT CON AGENTE**: chatta in-character. Esempi utili:
- 🔐 **DPO** ("posso conservare i dati cliente per newsletter?")
- 🛡 **CISO** ("ho ricevuto mail sospetta, cosa faccio?")
- 🦺 **RSPP** ("scadenze formazione del team?")
- 💰 **Admin** ("scadenze fiscali questo mese?")
- 💼 **Sales** ("bozza proposta per Cliente X")
- 🏢 **Client Onboarding** ("checklist nuovo cliente")
- 📜 **Privacy Scout** ("cosa ha detto Garante questa settimana?")
- 🏗 **Architect** ("voglio aggiungere agente sponsorizzazioni")

### I 4 tier

| Tier | Agenti |
|---|---|
| **0 Governance** | Steward, Architect |
| **1 Compliance** | DPO, CISO, RSPP, Audit Watcher |
| **2 Operations** | Admin, Sales, Email Manager, Report Builder, Client Onboarding, HR, Training, File Org, Knowledge Mgmt, Bug Hunter, Innovator, Marketing, AI Expert |
| **3 Intelligence** | Privacy / Cyber / Market / Compliance / Safety Scout |

---

## 🛠 Operations Center

Bottone **🛠**, modal con 5 sezioni:

| Tab | Cosa vedi |
|---|---|
| 🏥 HEALTH | Stato healthy / degraded / unhealthy + 9 componenti |
| 🔄 WORKFLOW | I 3 workflow consulting (run, history) |
| 📋 TASK QUEUE | Pending / running / ok / DLQ |
| 📜 LOG CENTER | Audit log + events + outbound |
| 🔍 TRACE | trace_id recenti per debug |

---

## ⚙ Impostazioni chiave

| Setting | Cosa fa |
|---|---|
| **Voce** | TTS italiana |
| **Modalità privata** | Conversazioni NON salvate |
| **Interrompi con voce** | Parla mentre Vega parla → si ferma (cuffie) |
| **Ascolto continuo** | No più "Vega" ogni volta (60s buffer) |
| **Sincronizza voce + testo** | Testo appare quando parte la voce |
| **Tema** | HUD scuro / Chiaro / Auto (orario) |
| **Local LLM** | Ollama per smalltalk (gratis, se installato) |
| **🏛 Team mode** | Sblocca i 31 agenti |

---

## 📅 Automatismi (gira da solo)

| Quando | Cosa |
|---|---|
| All'apertura del giorno | **Morning Briefing** (meteo + privacy + cyber + incident + proposte) |
| Daily 07:00 | Privacy Scout (Garante, Federprivacy, EDPB) |
| Daily 07:15 | Cyber Scout (CSIRT, CISA, ENISA, ACN) |
| Daily 07:30 | Compliance Scout (Agenzia Entrate, INPS, INAIL) |
| Daily 08:00 | Admin: alert scadenze fiscali -7gg |
| Weekly Lun 08:00 | RSPP: scadenze D.Lgs 81 |
| Weekly Lun 10:00 | HR: ferie, contratti, review |
| Weekly Ven 17:00 | Report Builder: report clienti |
| Weekly Dom 18:00 | Innovator: proposte feature |
| Monthly day 1 | Audit Watcher: compliance report |
| Monthly day 28 | Workflow `month_close` |
| Ogni 30min | Email Manager + News feed |
| Ogni 4h | Bug Hunter health |
| Ogni 6h | Audit chain integrity |

---

## 🛡 Sicurezza (tutto già attivo)

18 layer enterprise-grade: Bearer token, TLS opt-in, CORS allowlist, CSP, prompt shield, tool ACL, output filter (mask IBAN/CF/JWT), path guard, net guard (allowlist outbound), audit hash-chained, rate limit (5 PIN fail → lockout 15min), honeypot canary, CVE scanner, WS replay protection, .env vault, mic kill switch, privacy mode, DPO/CISO/RSPP agents.

---

## 🎯 Casi d'uso reali

**Mattina lavoro**: apri → vedi Morning Briefing → "leggi email" → "scadenze fiscali" → chiudi todo

**Nuovo cliente**: 🛠 → 🔄 → RUN `new_client_onboarding` → 5 agenti in cascata → 20 sec → fatto

**Domanda compliance**: 🏛 → 💬 → DPO → chiedi cosa vuoi (cita Art. GDPR pertinente)

**Aggiungi agente custom**: 🏛 → chat con Architect → "voglio agente per X" → genera codice live

---

## ❓ Problemi comuni

| Problema | Soluzione |
|---|---|
| Non sente "Vega" | Click pillola mic, verifica permessi browser |
| Voce strana | ⚙ → cambia voce |
| Vuole soldi | Setta `ANTHROPIC_API_KEY` in `.env` |
| Lento | 🛠 → 📊 cache hit (prima query è cold) |
| PIN sempre | Da localhost non serve; da LAN sì |
| Agente non risponde | 🏛 → verifica enabled / 🛠 → 🏥 health |
| Pulisci tutto | Cancella `data/` (ATTENZIONE: perdi memoria) |

---

## 🆕 Aggiornamenti maggio 2026

- ✨ **Morning Briefing** automatico
- ✨ **Operations Center 🛠** (5 tab tecniche)
- ✨ **Onboarding wizard** primo avvio
- ✨ **Tutorial 5 tab**
- ✨ **Tema chiaro/scuro/auto**
- ✨ **31 agenti** (era 11)
- ✨ **12 agenti consulting** rinforzati (Admin fiscale reale, RSPP D.Lgs 81, Sales CRM, ecc.)
- ✨ **Workflow runner**
- ✨ **Architect** che genera nuovi agenti
- ✨ **Sincronia voce+testo**
- ✨ **18 fix sicurezza enterprise**
- ✨ **Cost dashboard per agent/tool**
- ✨ **Memoria con freshness + decay + cluster entity**
- ✨ **RAG docs auto-injection**
- ✨ **Tool chaining hints + auto-disable**
- ✨ **Tracing trace_id**
- ✨ **Mobile PWA polish + accessibility**

---

## 📞 Setup nuovo PC

1. Python 3.14
2. Clona `vega/`
3. `setup.bat` da console
4. Configura `.env` con `ANTHROPIC_API_KEY`
5. Doppio click `Vega.vbs` (silent) o `Vega.bat`
6. Browser apre auto
7. Wizard onboarding ti accompagna

---

**Buon uso. Tieni un diario di cosa usi/non usi/manca: serve per il prossimo cleanup.**
