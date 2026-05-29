# 📋 VEGA — Cheat Sheet (1 pagina A4 stampabile)

## 🎙 ATTIVAZIONE
**"Vega"** · "ehi Vega" · "ok Vega" → aspetta bip → parla
**"Stop"** / **"Basta"** → interrompe

## ⚡ FRASI BASE
| Frase | Risultato |
|---|---|
| che ore sono | ora + data |
| che tempo fa | meteo card |
| leggimi le mail | inbox riassunto |
| apri Spotify / Word | lancia app |
| genera immagine di X | Pollinations gratis |
| imposta timer 10 min | timer |
| aggiungi todo: ... | salva |

## 🧠 FRASI AVANZATE
| Frase | Effetto |
|---|---|
| guarda lo schermo | analisi visuale |
| ricorda che ... | Mem0 persistente |
| dimmi cosa sai su X | dossier clusterizzato |
| pensaci bene su X | extended thinking |
| dibattito su X | 3 voci + sintesi |
| agente: ... | planner multi-step |
| missione: ... | autonomo long-horizon |

## 📱 BOTTONI TOPBAR
**❓** guida · **🩺** diagnosi · **🖥** PC · **📊** stats · **🏛** agenti · **💡** proposte · **🗂** card history · **🛠** ops center · **⚙** settings

## 🏛 CHAT AGENTI (in 🏛 → tab "💬 CHAT")
🔐 **DPO** GDPR · 🛡 **CISO** NIS2 · 🦺 **RSPP** D.Lgs 81 · 💰 **Admin** fisco · 💼 **Sales** CRM · 🏢 **Onboarding** · 📑 **Report** · 📜 **Privacy Scout** · 🛡 **Cyber Scout** · 🧠 **AI Expert** · 🏗 **Architect** crea agenti

## 🛠 OPERATIONS CENTER
🏥 Health · 🔄 Workflow · 📋 Queue · 📜 Log · 🔍 Trace

## ⌨ SCORCIATOIE
**F11** fullscreen · **Invio** invia · **Shift+Invio** newline · **Esc** chiude modal
**Drag & drop** file/immagini/PDF → analisi auto

## 🔐 PRIVACY
- Tutto locale, no cloud (eccetto API Anthropic HTTPS)
- **Modalità privata** in ⚙: conversazioni NON salvate
- **PIN** per accesso da LAN/mobile
- **Click mic pillola** in alto = mic OFF immediato

## 📅 AUTOMATICO
- Apertura mattina: Morning Briefing
- 07:00 Privacy Scout · 07:15 Cyber Scout · 07:30 Compliance Scout
- 08:00 Admin scadenze fiscali · Lun 08:00 RSPP sicurezza
- Ven 17:00 Report clienti · Dom 18:00 Innovator
- Day 28 mese: workflow `month_close`

## 🆘 PROBLEMI
| Problema | Fix |
|---|---|
| non sente Vega | click mic pillola, permessi browser |
| voce strana | ⚙ → cambia voce |
| chiede PIN sempre | da localhost no, da LAN sì |
| lento | 📊 cache hit (prima query cold) |
| pulisci tutto | cancella `data/` ⚠ |

## 🔗 API DEBUG
```
GET  /api/health                stato globale
GET  /api/health/ready          readiness 200/503
GET  /api/metrics/cache         hit rate
GET  /api/metrics/costs         costi agent/tool
GET  /api/team/status           31 agenti
POST /api/team/run              {agent, payload}
POST /api/team/chat             {agent, message}
POST /api/workflows/team/run    {workflow, payload}
GET  /api/trace/recent          ultimi trace
GET  /api/audit/tail?n=100      audit log
GET  /api/audit/verify          chain integrity
POST /api/architect/blueprint   crea blueprint
POST /api/architect/deploy      genera agenti
```

## 💸 COSTI
~**$1-3/mese** uso quotidiano. Riduci con: Local LLM (Ollama), Privacy mode, query brevi.

---
**Vega v.2026.05** · 8 layer · 31 agenti · 124 tool · 18 fix sicurezza enterprise · MIT
