# 🤝 Contributing a Vega

Grazie dell'interesse! Ecco come contribuire.

---

## Come iniziare

1. **Fork** il repo
2. **Clone** la tua fork
3. Crea un **branch** descrittivo: `git checkout -b feat/nuovo-agente-legale`
4. Setup: `setup.bat` o `./setup.sh`
5. Sviluppa
6. Test: `python tests/full_system_test.py`
7. **Pull Request** verso `main`

---

## Tipi di contributo benvenuti

### 🐛 Bug fix
- Apri prima un Issue descrivendo il bug + reproduce steps
- Allega un test se possibile

### ✨ Nuove feature
- Apri prima un Issue per discuterla (evita lavoro sprecato)
- Mantieni la coerenza con i layer architetturali (vedi ARCHITECTURE.md)

### 🏛 Nuovi template industry
Cerchiamo template oltre `consulting_smb`:
- `legal_smb` (studio legale)
- `ecommerce_smb` (negozio online)
- `healthcare_smb` (studio medico)
- `real_estate` (agenzia immobiliare)
- `accountant` (commercialista)
- `training_provider` (formazione)

Vedi `data/agent_templates/consulting.json` come riferimento.

### 🌍 Traduzioni
Vega nasce in italiano. Traduzioni di system prompt + UI in altre lingue benvenute.

### 🎨 UI/UX
Polish del HUD theme, accessibility, mobile responsive — sempre apprezzati.

### 📚 Documentazione
Refining `GUIDA_UTENTE.md`, traduzioni guida, video tutorial.

---

## Linee guida codice

### Python
- **Style**: PEP 8 (no formatter forzato, ma leggibile)
- **Type hints**: incoraggiati ma non obbligatori
- **Docstrings**: una riga per funzione/classe pubblica
- **Niente import top-level pesanti**: usa import lazy dentro funzioni se rallenta boot
- **No print()**: usa `bus.publish("warning", ...)` per logging

### Nuovi agenti
Estendono `TeamAgent` (vedi `agents/team_base.py`):

```python
from .team_base import TeamAgent

class NuovoAgent(TeamAgent):
    name = "nuovo_agente"
    tier = 2  # 0/1/2/3
    icon = "🎯"
    description = "Descrizione breve"
    model_pref = "haiku"  # haiku/sonnet/local
    schedule = "daily 09:00"  # opzionale
    subscribes = []  # bus topics

    def run(self, payload):
        op = (payload or {}).get("op", "default")
        if op == "default":
            # logica
            return {"ok": True, "result": ...}
        return {"ok": False, "error": "op sconosciuta"}

AGENT = NuovoAgent()
```

### Nuovi tool
Vedi `tools/*.py` come riferimento. Pattern:

```python
TOOLS = [{
    "name": "nuovo_tool",
    "description": "Descrizione chiara per Claude (include [LIVE]/[CACHED] hint)",
    "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...],
    },
}]


def run(name, args):
    # implementazione
    return result  # str o list di blocchi
```

Registra in `tools/__init__.py`.

### Sicurezza
- **MAI** committare `.env`, chiavi API, password
- Verifica `.gitignore` prima di push
- Per tool sensibili, aggiungi a `tool_acl.HIGH_RISK`
- Network calls: aggiungi domini a `net_guard.DEFAULT_ALLOWLIST`

---

## Testing

```bash
# Full system test
python tests/full_system_test.py

# Red team security tests
python tests/security_redteam.py
```

Se aggiungi una feature security, aggiungi anche un red team test.

---

## Commit message convention

Usa un prefisso per chiarezza:

- `feat:` nuove feature
- `fix:` bug fix
- `docs:` documentazione
- `refactor:` refactoring senza cambio comportamento
- `test:` solo test
- `chore:` dependency update, build, ecc.
- `security:` security fix (priorità top)

Esempio:
```
feat(agents): add legal template with 8 specialized agents

Implements consulting_legal template:
- Notary, paralegal, court-watcher, contract-reviewer, …
- Updates Architect template registry
- Adds 3 new workflows: case_open, settlement, archive

Closes #42
```

---

## Pull Request checklist

- [ ] Test passano (`full_system_test.py`)
- [ ] Codice formattato pulito
- [ ] Niente `.env` o secret committati
- [ ] Documentazione aggiornata (se feature visibile a utente)
- [ ] CHANGELOG (se esiste) aggiornato
- [ ] PR description chiara con rationale + screenshot se UI

---

## Code of Conduct

Sii rispettoso. No tolerance per harassment.
Critica il codice, non le persone.
Le PR vengono valutate sul merito tecnico.

---

## Domande

Apri un Issue con label `question` o contatta il maintainer.

**Grazie!**
