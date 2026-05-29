# 🎬 Script video walkthrough Vega

6 video, 3-5 minuti ciascuno. Registrare con OBS Studio o Loom mentre usi davvero Vega.

---

## VIDEO 1 — "Cos'è Vega in 3 minuti"

**Durata**: 3 min · **Pubblico**: chi non l'ha mai visto

### Scaletta
- **[0:00-0:15]** Hook: "Questo è il mio assistente AI personale. Vive sul mio PC. Non manda nulla nel cloud — a parte le chiamate AI. Te lo mostro in 3 minuti."
- **[0:15-0:45]** Voce: "Vega, che tempo fa?" → risposta + card meteo
- **[0:45-1:15]** Memoria: "Vega, ricorda che ho un gatto Pepe" → poi "Come si chiama il mio gatto?"
- **[1:15-2:00]** Drag PDF → riassunto. Drag immagine → "lui la vede"
- **[2:00-2:45]** Tour 🏛: "31 esperti virtuali. DPO, CISO, Sales…"
- **[2:45-3:00]** CTA: "GUIDA_UTENTE.md. CHEAT_SHEET.md. Buon uso."

**Chiusura**: "31 agenti, 124 tool, e tutto resta tuo."

---

## VIDEO 2 — "Parla con i tuoi 31 esperti virtuali"

**Durata**: 5 min

### Scaletta
- **[0:00-0:30]** Concept: apri 🏛 → "non un assistente, un team"
- **[0:30-1:30]** Tour dei 4 tier (Governance, Compliance, Operations, Intelligence)
- **[1:30-3:00]** Chat con 🔐 DPO esempio reale: "Ho lista tesserati club. Posso usarla per newsletter Natale?" → risposta in-character con Art. GDPR
- **[3:00-4:00]** Chat con 💼 Sales: "Bozza proposta consulenza 3 mesi €4500 per Studio Bianchi"
- **[4:00-5:00]** Pannello LIVE MESSAGES: spiega bus inter-agent

**Chiusura**: "Non un chatbot. Un consiglio di amministrazione virtuale."

---

## VIDEO 3 — "Workflow: 5 cose insieme con un click"

**Durata**: 4 min · **Pubblico**: consulenti pro

### Scaletta
- **[0:00-0:30]** Problema: "Nuovo cliente = apri 5 tool, registri Art. 30, crei cartella… 20 minuti."
- **[0:30-1:30]** Demo: 🛠 → 🔄 → ▶ RUN `new_client_onboarding` → card live con 5 step verdi
- **[1:30-2:30]** Cosa è successo: apri `data/clients.json`, `data/gdpr_register.json`, `data/client_files/`, `data/admin_invoices.json`, `data/sales_leads.json`
- **[2:30-3:30]** Workflow `month_close`: stesso click, fattura tutti + report mensili + lessons learned + audit
- **[3:30-4:00]** Custom: "modifica consulting.json o chiedi all'Architect"

**Chiusura**: "20 minuti diventano 20 secondi."

---

## VIDEO 4 — "Sicurezza: 18 layer enterprise"

**Durata**: 5 min · **Pubblico**: cybersec/privacy pro

### Scaletta
- **[0:00-0:30]** Threat model: "Se gestisce dati clienti, deve essere serio"
- **[0:30-1:30]** Network: Bearer + PIN + Net guard (mostra `data/outbound.log.jsonl`)
- **[1:30-2:30]** AI-specific: prompt shield, tool ACL, output filter (IBAN/CF/JWT mascherati)
- **[2:30-3:30]** Audit: 🛠 → 📜 → hash chain + `/api/audit/verify`
- **[3:30-4:30]** Honeypot canary: `data/canaries.json` — "se appaiono in output = leak confermato"
- **[4:30-5:00]** Daily: CVE scanner + scout cyber/privacy + chat DPO/CISO/RSPP

**Chiusura**: "Non sostituisce un DPO/CISO umano. Lo affianca."

---

## VIDEO 5 — "Memoria che dura davvero"

**Durata**: 3 min

### Scaletta
- **[0:00-0:30]** Problema ChatGPT: "Dimentica tutto a fine chat. Vega no."
- **[0:30-1:15]** Mem0: "Cliente Studio Bianchi, arredamento, 200K fatturato, 3 collab" → chiudi/riapri → "Cosa sai di Studio Bianchi?" → risposta completa
- **[1:15-2:00]** Cluster: "Dimmi tutto quello che sai su Studio Bianchi" → dossier raggruppato
- **[2:00-2:30]** Freshness boost: nota di ieri pesa 1.20×, di un anno fa 1.05× (decay)
- **[2:30-3:00]** RAG: carica PDF in `data/rag_docs/` → fai domanda → "trova chunk rilevanti"

**Chiusura**: "Memoria multi-livello: episodica + graph + RAG + news. Niente si perde."

---

## VIDEO 6 — "Crea il tuo agente in 60 secondi"

**Durata**: 4 min · **Pubblico**: tech-savvy

### Scaletta
- **[0:00-0:30]** Concept: "Vuoi agente sponsorizzazioni? Lo crei parlandone."
- **[0:30-1:30]** Discovery: 🏛 → chat 🏗 Architect → "voglio agente sponsorizzazioni" → 7 domande
- **[1:30-2:30]** Blueprint: mostra JSON con tier 2, tool, schedule
- **[2:30-3:30]** Deploy: mostra `agents/sponsorizzazioni.py` generato live + AST + smoke + hot-reload → compare in 🏛
- **[3:30-4:00]** Test: click ▶ Run sul nuovo agente

**Chiusura**: "Architect è l'agente che fa agenti. Meta è bello."

---

## 📝 Tips registrazione

### Setup
- **OBS Studio** 1920x1080 30fps
- Headset decente per audio (mute audio sistema)
- Mouse highlight + click ripple
- Hotkeys-overlay opzionale

### Editing
- Taglia pause >1.5 sec
- Chapter marks ogni 30 sec
- Titoli grandi cyan (matching HUD)
- Musica Lo-fi bassissima

### Distribuzione
- YouTube **unlisted** prima (test feedback)
- LinkedIn post breve + link
- GitHub README embed
- TikTok/Reels: video 1 in formato 9:16

### Tono voiceover
- Calmo, conciso, no entusiasmo finto
- Prima persona ("io")
- Esempi reali (anche se fittizi: "Studio Bianchi" è un cliente immaginario)

---

## Storyboard alternativa: Reel 30 sec

```
[0:00] Schermo nero
"Mi sono costruito un assistente AI."

[0:03] Apro Vega, sfera cyan pulsa
"Vive sul mio PC."

[0:06] "Vega, leggi le mie mail"
[0:09] Riassunto vocale + card

[0:12] Click 🏛
"31 esperti virtuali."

[0:15] Tier mostrati
"Privacy, cybersec, sicurezza lavoro."

[0:18] Chat DPO → "Posso conservare dati cliente?"
[0:21] Risposta con Art. GDPR

[0:24] Cut a 🛠 Operations Center
"Audit log immutabile."

[0:27] GitHub
"Open source."

[0:30] Logo Vega
```

Fine.
