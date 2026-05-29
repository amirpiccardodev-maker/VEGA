# 🏗 Architettura Vega

Documento tecnico per chi vuole capire/contribuire.

## Vista d'insieme

Vega è strutturato in **8 layer architetturali**. Ogni layer ha responsabilità singola, comunica via interfacce definite, può essere disabilitato senza rompere gli altri.

```
                ┌──────────────────────┐
                │   USER (voce/UI)     │
                └──────────┬───────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │  L7  UI/UX & PWA  — HTML/CSS/JS + WebSocket │
       └───────────────────┬─────────────────────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │  L1  VOICE & AUDIO  — Whisper + Edge-TTS    │
       └───────────────────┬─────────────────────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │  L5  TEAM AGENTICO  — 31 agenti, 4 tier     │
       └───────────────────┬─────────────────────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │  L2  BRAIN  — Sonnet + Haiku + Ollama       │
       └─────┬────────────┬────────────┬─────────────┘
             │            │            │
       ┌─────▼─────┐  ┌───▼────┐  ┌────▼─────┐
       │ L3 MEMORIA│  │ L4 TOOL│  │ L6 SECURITY │
       └───────────┘  └────────┘  └──────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │  L8  INFRA  — Bus + Queue + Workflow + Tracing │
       └─────────────────────────────────────────────┘
```

## I layer

### L1 — Voice & Audio
**File**: `engine.py`, `tts.py`
- Whisper STT (`base` model, int8, VAD filter, initial_prompt italiano)
- openWakeWord + fallback Whisper su frasi italiane
- Edge-TTS primario + ElevenLabs opzionale + cache disco
- Voice biometrics (resemblyzer) per identificare lo speaker
- Voice interrupt: RMS thread durante TTS playback
- Always-on opt-in (60s finestra)
- Sync voce+testo client-side

### L2 — Brain & Reasoning
**File**: `brain.py`, `fast_brain.py`, `local_brain.py`, `debate.py`, `agent_fabric.py`, `cost_tracker.py`, `batch_brain.py`
- Sonnet 4.5 main + prompt caching 2-livelli (static + dynamic)
- Haiku 4.5 per routing/summary/agent codegen
- Ollama (opt-in) per smalltalk gratis
- Extended thinking adattivo (2K/5K/10K/15K)
- Debate 3 voci (ottimista/pessimista/pragmatico)
- agent_fabric Planner/Executor/Verifier
- long_horizon autonomous loop
- Summary trigger su token count (>12K) non message count
- Cost tracking SQLite per-caller

### L3 — Memoria & Knowledge
**File**: `memory_graph.py`, `episodic_memory.py`, `news_graph.py`, `memory_dedup.py`, `honeypot.py`, `tools/rag.py`
- memory_graph: SQLite + paraphrase-multilingual-MiniLM-L12-v2 embeddings
  - 8 kinds: fact/note/todo/instruction/conversation/procedure/episodic/news
  - Search con freshness boost + decay esponenziale (half-life 365gg)
  - Multi-tenant via `tenant_id`
- Mem0 episodic con LLM extraction (Haiku-based) + Chroma locale
- news_graph: 5+ RSS feeds, ogni 30min
- memory_dedup weekly cross-search
- Honeypot canary (3 strings)
- RAG docs auto-injection nel system prompt (similarity>0.55)
- Cluster by entity (`cluster_by_entity(name)`)

### L4 — Tool Ecosystem
**File**: `tools/__init__.py` + 50+ modules, `tool_cache.py`, `tool_health.py`, `tool_acl.py`, `tool_chain.py`, `prompt_shield.py`, `path_guard.py`
- 124+ tool registrati
- ACL: HIGH risk richiede PIN session
- Cache LRU 5min + version-based invalidation
- Health: ring buffer 20, auto-disable se fail rate >70%
- Chain hints: suggerisce prossimo tool
- Shield: 5 categorie injection
- Path guard: whitelist root + null-byte/Win reserved block
- Progress feedback per tool >1.5s

### L5 — Team Agentico
**File**: `agents/team_base.py`, `agents/team_registry.py`, `agents/<31 moduli>`, `agents/chat_personas.py`, `workflow_runner.py`
- 31 agenti:
  - Tier 0 (2): Steward, Architect
  - Tier 1 (4): DPO, CISO, RSPP, Audit Watcher
  - Tier 2 (16): 12 consulting + 4 core
  - Tier 3 (5): Scout daily
  - Monitors (7): brain, memory, voice, security, network, task, health
- Architect codegen scaffold-based (LLM solo body di run())
- Workflow runner: 3 workflow consulting (`new_client_onboarding`, `month_close`, `project_close`)
- Chat personas con "never give up" universal rule
- Dynamic registry: scopre agenti generati run-time

### L6 — Security
**File**: `auth.py`, `tls_setup.py`, `prompt_shield.py`, `tool_acl.py`, `net_guard.py`, `audit_log.py`, `rate_limit.py`, `honeypot.py`, `cve_scanner.py`, `output_filter.py`, `path_guard.py`, agents/dpo.py, ciso.py, rspp.py

18 layer attivi (vedi README per elenco). Allineati GDPR + NIS2 + D.Lgs 81 + ISO 27001.

### L7 — UI/UX & PWA
**File**: `ui/index.html`, `ui/vega.js`, `ui/style.css`, `ui/theme.css`, `ui/sw.js`, `ui/manifest.json`
- UI liquida generativa: orb WebGL (fragment shader fbm/fresnel) che respira e reagisce alla voce, palette periwinkle/indigo VEGA, fallback canvas 2D + glassmorphism
- PWA installable + service worker
- Modal: Settings, Help (5 tab), Automation Mode (Board+Chat), Ops Center (5 tab), Search, Stats, Diagnose, Onboarding wizard
- Drag & drop file upload
- Theme dark/light/auto
- A11y: focus-visible rings, skip link, prefers-contrast/reduced-motion
- Mobile: safe-area iOS, tap ≥44px, swipe pan

### L8 — Infrastruttura
**File**: `bus.py`, `task_queue.py`, `workflow_engine.py`, `workflow_runner.py`, `automations.py`, `tracing.py`, `telemetry_db.py`, `health.py`, `observability.py`
- Event bus in-process (sync + JSONL replay)
- Task queue SQLite WAL + workers + retry exp backoff + DLQ
- Workflow engine JSON DSL
- Scheduler cron-like
- Tracing trace_id per request, span persistiti
- Telemetry SQLite con retention 30gg
- Health endpoint /api/health{,/live,/ready}
- Hot-reload UI
- SQLite WAL + busy_timeout 30s + temp_store=MEMORY

## Decisioni di design (ADR)

### ADR-001: SQLite invece di PostgreSQL
Self-hosted single-user, no overhead server DB. WAL supporta concorrenza adeguata.

### ADR-002: Anthropic-only per main brain
Prompt caching ottimale, tool use stabile. Vendor lock-in mitigato da Ollama fallback.

### ADR-003: In-process bus invece di Kafka
Single-machine, ~10k events/sec sufficienti. Niente HA (accettato).

### ADR-004: Agenti come moduli Python diretti
Massima ispezionabilità, no DSL custom. Niente "framework di framework".

### ADR-005: Mem0 + memory_graph coesistenti
Mem0 fa LLM extraction; memory_graph fa filtri kind/tenant. Dedup weekly.

### ADR-006: PWA invece di Electron
Zero overhead, accesso LAN naturale, update istantanei. Niente OS-deep integration.

### ADR-007: Scaffold-based codegen per Architect
LLM genera spesso syntax errors su moduli interi. Scaffold + solo body è affidabile.

### ADR-008: 31 agenti single-process
GIL Python limita CPU-bound ma 95% del tempo è I/O. OK.

## Flussi chiave

### Richiesta utente vocale
```
1. Wake word → engine.listen
2. Whisper transcribe (~300ms)
3. shortcuts.try_match (regex, no LLM)
4. semantic_shortcuts.match_intent (embeddings)
5. local_brain.should_use_local? → Ollama
6. brain.ask_stream (Sonnet + cache + tool use)
7. Tool result → prompt_shield → tool_chain → output_filter
8. TTS pre-synth + playback parallelo
9. UI sync testo/voce
10. Mem0 episodic save background
11. cost_tracker.record + memory.record_usage
```

### Workflow new_client_onboarding
```
1. POST /api/workflows/team/run
2. workflow_runner carica JSON, builds shared_ctx
3. Step 1 client_onboarding.welcome_kit → 8-step checklist
4. Step 2 dpo.register_treatment → Art. 30
5. Step 3 file_organizer.create_client_folder
6. Step 4 admin.create_invoice_template
7. Step 5 sales.set_lead_status_won
8. Card UI + run salvato in data/workflow_runs/
```

### Architect generate agent
```
1. discovery 7 domande
2. build_blueprint from template
3. deploy_blueprint per ogni agente:
   a. _generate_agent_code (scaffold + Haiku + retry)
   b. _validate_code (AST walk + forbidden imports)
   c. _smoke_test (import + structure)
   d. file move _pending/ → agents/
4. team_registry.reload
5. Audit log
```

## Performance

- Cold start: ~8-12s (lazy load)
- Warm PWA: ~2-3s
- First voice query: ~3-5s (Whisper warmup)
- Subsequent: ~1-2.5s (cache hit)
- Tool avg: ~150ms cached / ~2-5s network
- Memory search: ~50-200ms
- Cache hit rate target: >40% (dopo 5-10 query)

## Estensione

### Aggiungere tool
1. `tools/my_tool.py` con `TOOLS = [{...}]` + `def run(name, args)`
2. Auto-discovery al boot
3. Opzionale: `TOOL_VERSIONS["my_tool"] = "v1"` in `tool_cache.py`

### Aggiungere agente
1. Manuale: `agents/my_agent.py` ereditando `TeamAgent`, esponi `AGENT`
2. Auto: chatta con Architect

### Aggiungere workflow
Modifica `data/agent_templates/consulting.json` (o nuovo template) con `workflows`.

### Persona chat
Aggiungi entry in `agents/chat_personas.py` `PERSONAS`.

## Test

```bash
venv/Scripts/python.exe tests/full_system_test.py     # 45/46 PASS
venv/Scripts/python.exe tests/security_redteam.py     # 36/36 PASS
```

## Roadmap (non promesse)

- Computer Use API integration
- Mobile nativa (Flutter/Capacitor)
- Vision streaming live (webcam)
- Multi-tenant deep
- Federazione multi-device CRDT
- Templates industry: legal, ecommerce, healthcare
- Claude Agent SDK migration
- Anthropic Managed Agents quando GA
