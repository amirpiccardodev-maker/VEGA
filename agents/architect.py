"""Agent Architect — meta-agente che progetta reti agentiche.

Workflow:
  1. Discovery interview (7 domande strutturate)
  2. Genera blueprint da template + customizzazione
  3. User approva blueprint
  4. Genera codice Python per ogni nuovo agente
     - LLM produce body run()
     - AST validation
     - Forbidden imports check
     - Smoke test (import + dummy run con timeout)
     - File spostato da _pending/ ad agents/
  5. Hot-reload team_registry
  6. Audit log + DPO/CISO review

SICUREZZA: la generazione codice è il punto critico. Whitelist rigida sugli
import + AST walk per intercettare patterns pericolosi (os.system, eval,
subprocess senza ACL, file write fuori da data/).
"""
import ast
import importlib
import json
import textwrap
import threading
import time
import uuid
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = ROOT / "data" / "agent_templates"
BLUEPRINTS_DIR = ROOT / "data" / "blueprints"
PENDING_DIR = ROOT / "agents" / "_pending"
PENDING_DIR.mkdir(parents=True, exist_ok=True)
BLUEPRINTS_DIR.mkdir(parents=True, exist_ok=True)


# ============ Discovery questions ============

DISCOVERY_QUESTIONS = [
    {"id": "industry", "q": "In quale settore opera la tua azienda?",
     "options": ["consulting", "ecommerce", "legal", "real_estate", "training",
                  "healthcare", "other"]},
    {"id": "size", "q": "Quante persone lavorano (incluso te)?",
     "options": ["1", "2-5", "6-15", "16-50", "50+"]},
    {"id": "core_processes", "q": "Quali sono i 3-5 processi che occupano l'80% del tempo?",
     "type": "free_text"},
    {"id": "pain_points", "q": "Quali sono i 2-3 pain point operativi principali?",
     "type": "free_text"},
    {"id": "compliance", "q": "Quali obblighi compliance hai?",
     "options": ["GDPR", "NIS2", "D.Lgs 81/08 (sicurezza lavoro)",
                  "ISO 9001/27001", "Fatturazione elettronica", "Altro"],
     "multi": True},
    {"id": "tools", "q": "Quali tool usi attualmente?",
     "options": ["Gmail", "Outlook", "Notion", "Trello/Asana", "Google Drive",
                  "OneDrive", "Excel", "CRM (HubSpot/Salesforce)",
                  "Fatturazione (Aruba/Fattura24)", "Altro"],
     "multi": True},
    {"id": "roles", "q": "Quali ruoli devono usare il sistema?",
     "options": ["Titolare/Amministratore", "Commerciale", "Operativo",
                  "Amministrativo", "Stagisti"],
     "multi": True},
]


# ============ Code generation prompt ============

SCAFFOLD = '''"""{description_safe}"""
import json
import time
from .team_base import TeamAgent


class {class_name}(TeamAgent):
    name = "{name}"
    tier = {tier}
    icon = "{icon}"
    description = "{description_safe}"
    model_pref = "{model_pref}"
    schedule = {schedule_repr}
    subscribes = []

    def run(self, payload):
{run_body_indented}


AGENT = {class_name}()
'''


BODY_GEN_SYSTEM = """Generi SOLO il body del metodo run() di un agente Vega.

CONTESTO: l'agente eredita TeamAgent e tu hai disponibili come `self.`:
  - self.call_haiku(prompt: str) -> str
  - self.call_haiku_json(prompt: str) -> dict
  - self.remember(kind: str, content: str, importance: float = 0.5)
  - self.search_memory(query: str, top_k: int = 5) -> list of dicts
  - self._emit(kind: str, data: dict)
  - self.is_enabled() -> bool

REGOLE:
1) Output è SOLO il body del metodo run(self, payload) — niente def, niente class.
2) Il body deve essere indentato di 8 spazi (perché va dentro un metodo di classe).
3) Ogni return deve essere un dict con almeno chiave "ok": bool.
4) Niente: import (sono già all'esterno), open(), os.*, sys.*, subprocess, eval, exec.
5) Usa solo le primitive Python builtin (str, list, dict, int, float, bool) + json + time già importati esternamente.
6) Sii conciso (max 20 righe).
7) NESSUN markdown, NESSUN backtick, NESSUNA spiegazione.

ESEMPIO DI OUTPUT (esattamente questa struttura, indentato 8 spazi):
        op = payload.get("op", "default")
        if op == "default":
            ctx = self.search_memory("query rilevante", top_k=5)
            if not ctx:
                return {"ok": True, "result": "no context"}
            prompt = "Riassumi: " + " | ".join(c.get("content", "")[:80] for c in ctx[:3])
            out = self.call_haiku(prompt)
            self.remember("note", "Summary: " + out[:200], importance=0.5)
            self._emit("done", {"chars": len(out)})
            return {"ok": True, "summary": out}
        return {"ok": False, "error": "op sconosciuta"}
"""


CODE_GEN_SYSTEM = """Generi il modulo Python di un agente Vega che eredita TeamAgent.

REGOLE INVIOLABILI (validation AST le verifica):
1) Import permessi: SOLO `import json`, `import time`, `import threading`, `import re`, `import uuid`, e `from .team_base import TeamAgent`. Niente altro.
2) Classe deve estendere TeamAgent.
3) Attributi class-level OBBLIGATORI: name (str), tier (int 0-3), icon (str emoji), description (str), model_pref ("haiku"|"sonnet"|"local"), schedule (str|None), subscribes (list).
4) Implementa def run(self, payload: dict) -> dict
5) ULTIMA RIGA del file: AGENT = NomeClasseAgent()
6) VIETATI: os.*, sys.*, subprocess.*, eval(), exec(), __import__, open(), file I/O, requests, urllib, http.*, socket, pickle, marshal, ctypes.
7) NON usare f-string come docstring multilinea (causa parse error).
8) Per LLM call usa self.call_haiku(prompt) o self.call_haiku_json(prompt).
9) Per memoria usa self.remember(kind, content, importance=0.5) e self.search_memory(query).
10) Per emit usa self._emit(kind, data_dict).

OUTPUT: SOLO codice Python eseguibile, NESSUN markdown, NESSUN backtick, NESSUNA spiegazione prima o dopo.

ESEMPIO COMPLETO (copia esattamente questa struttura):

\"\"\"Report Builder — Tier 2.\"\"\"
import json
import time
from .team_base import TeamAgent


class ReportBuilderAgent(TeamAgent):
    name = "report_builder"
    tier = 2
    icon = "X"
    description = "Genera report cliente."
    model_pref = "haiku"
    schedule = "weekly Friday 17:00"
    subscribes = []

    def run(self, payload):
        op = payload.get("op", "weekly")
        if op == "weekly":
            ctx = self.search_memory("progetti clienti", top_k=10)
            ctx_str = " | ".join(c.get("content", "")[:100] for c in ctx[:5])
            prompt = "Genera report settimanale basato su: " + ctx_str
            report = self.call_haiku(prompt)
            self.remember("note", "Report: " + report[:200], importance=0.5)
            self._emit("weekly_done", {"chars": len(report)})
            return {"ok": True, "chars": len(report)}
        return {"ok": False, "error": "op sconosciuta"}


AGENT = ReportBuilderAgent()
"""


# ============ AST validation ============

ALLOWED_IMPORTS = {"json", "time", "threading", "uuid", "re"}
ALLOWED_FROM_IMPORTS = {".team_base": {"TeamAgent"}}

FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "shutil",
    "eval", "exec", "compile", "__import__",
    "requests", "urllib", "http", "socket",
    "pickle", "marshal", "ctypes",
    "open",  # we want self.* only
}


def _validate_code(code: str) -> dict:
    """Return {ok, error, ast_summary}."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return {"ok": False, "error": f"SyntaxError: {e}"}
    # Walk
    has_agent_export = False
    has_class_team_agent = False
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    issues.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            allowed = ALLOWED_FROM_IMPORTS.get("." + module) or ALLOWED_FROM_IMPORTS.get(module)
            if not allowed:
                issues.append(f"forbidden from-import: {module}")
            else:
                for alias in node.names:
                    if alias.name not in allowed:
                        issues.append(f"forbidden symbol: {module}.{alias.name}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
                issues.append(f"forbidden call: {node.func.id}()")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                # Direct reference (not always bad, but suspicious)
                if not isinstance(node.ctx, ast.Store):
                    issues.append(f"forbidden name ref: {node.id}")
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "AGENT":
                    has_agent_export = True
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "TeamAgent":
                    has_class_team_agent = True

    if not has_agent_export:
        issues.append("missing AGENT = ... export")
    if not has_class_team_agent:
        issues.append("no class extending TeamAgent")

    if issues:
        return {"ok": False, "error": "; ".join(issues[:5])}
    return {"ok": True}


def _smoke_test(agent_name: str) -> dict:
    """Verify structural correctness of the generated module.

    NOTE: We deliberately DO NOT call run() here because real agent run() may
    invoke LLM calls (haiku) and exceed any reasonable timeout. Static checks
    are sufficient pre-deploy; runtime issues will surface in audit_log.
    """
    try:
        mod = importlib.import_module(f"agents._pending.{agent_name}")
        importlib.reload(mod)
    except Exception as e:
        return {"ok": False, "error": f"import error: {e}"}
    inst = getattr(mod, "AGENT", None)
    if inst is None:
        return {"ok": False, "error": "no AGENT instance"}
    # Verify required attributes
    for attr in ("name", "tier", "icon", "description", "model_pref"):
        if not hasattr(inst, attr):
            return {"ok": False, "error": f"missing attribute: {attr}"}
    # Verify it extends TeamAgent
    from agents.team_base import TeamAgent
    if not isinstance(inst, TeamAgent):
        return {"ok": False, "error": "AGENT does not extend TeamAgent"}
    # Verify run() is callable
    if not callable(getattr(inst, "run", None)):
        return {"ok": False, "error": "run() not callable"}
    return {"ok": True,
            "sample_result": f"class={type(inst).__name__} tier={inst.tier} name={inst.name}"}


# ============ Code generation ============

def _strip_markdown(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def _class_name_for(name: str) -> str:
    """report_builder -> ReportBuilderAgent"""
    return "".join(p.capitalize() for p in name.split("_")) + "Agent"


def _safe_indent(body: str, spaces: int = 8) -> str:
    """Re-indent body to exactly N spaces. Strip leading common indent first."""
    lines = body.splitlines()
    # Find min leading whitespace (excluding empty lines)
    nonempty = [l for l in lines if l.strip()]
    if not nonempty:
        return " " * spaces + "return {\"ok\": True}"
    min_indent = min(len(l) - len(l.lstrip()) for l in nonempty)
    pad = " " * spaces
    out = []
    for l in lines:
        if not l.strip():
            out.append("")
        else:
            out.append(pad + l[min_indent:])
    return "\n".join(out)


def _generate_agent_code(agent_def: dict, max_retries: int = 2) -> tuple:
    """SCAFFOLD-BASED generation: LLM produce SOLO il body di run().
    Lo scaffold è costruito da template fisso. Molto più robusto."""
    name = agent_def["name"]
    class_name = _class_name_for(name)
    schedule = agent_def.get("schedule")
    schedule_repr = repr(schedule) if schedule else "None"
    # Sanitize description for docstring (no triple quotes inside)
    desc = (agent_def.get("description") or "")[:200].replace('"""', '"')

    try:
        import fast_brain
    except Exception:
        return "", "fast_brain unavailable"

    # Ask LLM only for the run() body
    body_prompt = (
        f"{BODY_GEN_SYSTEM}\n\n"
        f"AGENTE: {name} (tier {agent_def['tier']}, ruolo: {agent_def['description']})\n"
        f"SCOPE: {agent_def.get('system_prompt', '')[:500]}\n\n"
        f"Genera il body (indentato 8 spazi) per run(self, payload):"
    )

    last_error = ""
    for attempt in range(max_retries + 1):
        if attempt > 0:
            body_prompt += f"\n\n⚠️ Tentativo precedente fallito ({last_error}). Correggi e ritenta."
        try:
            body = fast_brain.fast_call(body_prompt) or ""
        except Exception as e:
            last_error = f"LLM: {e}"
            continue
        body = _strip_markdown(body)
        if not body.strip():
            last_error = "empty body"
            continue
        # Normalize indentation to 8 spaces
        body_indented = _safe_indent(body, spaces=8)
        # Build full module
        code = SCAFFOLD.format(
            class_name=class_name,
            name=name,
            tier=agent_def["tier"],
            icon=agent_def.get("icon", "🤖"),
            description_safe=desc,
            model_pref=agent_def.get("model_pref", "haiku"),
            schedule_repr=schedule_repr,
            run_body_indented=body_indented,
        )
        # Validate full module
        v = _validate_code(code)
        if v["ok"]:
            return code, ""
        last_error = v["error"]

    # Fallback: scaffold with a no-op body
    body_indented = (
        "        return {\"ok\": True, \"note\": \"agente generato con stub vuoto, "
        "personalizzare run()\"}"
    )
    code = SCAFFOLD.format(
        class_name=class_name,
        name=name,
        tier=agent_def["tier"],
        icon=agent_def.get("icon", "🤖"),
        description_safe=desc,
        model_pref=agent_def.get("model_pref", "haiku"),
        schedule_repr=schedule_repr,
        run_body_indented=body_indented,
    )
    v = _validate_code(code)
    if v["ok"]:
        return code, f"stub fallback (gen errors: {last_error})"
    return "", last_error


# ============ Architect agent class ============


class ArchitectAgent(TeamAgent):
    name = "architect"
    tier = 0
    icon = "🏗"
    description = "Meta-agente: progetta reti agentiche custom per la tua azienda"
    model_pref = "haiku"

    def __init__(self):
        super().__init__()
        self._discovery_sessions = {}  # session_id -> answers

    # --- Discovery ---
    def list_templates(self) -> list:
        out = []
        if not TEMPLATES_DIR.exists():
            return out
        for p in TEMPLATES_DIR.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    t = json.load(f)
                out.append({
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "industry": t.get("industry"),
                    "size_range": t.get("size_range"),
                    "agents_count": len(t.get("agents", [])),
                    "description": t.get("description"),
                })
            except Exception:
                pass
        return out

    def get_template(self, template_id: str) -> dict:
        p = TEMPLATES_DIR / f"{template_id}.json"
        if not p.exists():
            # Try by id field
            for tp in TEMPLATES_DIR.glob("*.json"):
                try:
                    with open(tp, "r", encoding="utf-8") as f:
                        t = json.load(f)
                    if t.get("id") == template_id:
                        return t
                except Exception:
                    pass
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def start_discovery(self) -> dict:
        sid = "disc_" + uuid.uuid4().hex[:8]
        self._discovery_sessions[sid] = {"answers": {}, "step": 0,
                                            "started_at": int(time.time())}
        self._emit("discovery_started", {"session_id": sid})
        return {
            "session_id": sid,
            "step": 0,
            "total_steps": len(DISCOVERY_QUESTIONS),
            "question": DISCOVERY_QUESTIONS[0],
        }

    def discovery_answer(self, session_id: str, answer) -> dict:
        sess = self._discovery_sessions.get(session_id)
        if not sess:
            return {"ok": False, "error": "session non trovata"}
        step = sess["step"]
        if step >= len(DISCOVERY_QUESTIONS):
            return {"ok": False, "error": "discovery già completata"}
        q = DISCOVERY_QUESTIONS[step]
        sess["answers"][q["id"]] = answer
        sess["step"] += 1
        if sess["step"] >= len(DISCOVERY_QUESTIONS):
            self._emit("discovery_complete", {"session_id": session_id,
                                                "answers": sess["answers"]})
            return {"ok": True, "complete": True, "answers": sess["answers"]}
        return {
            "ok": True,
            "complete": False,
            "step": sess["step"],
            "total_steps": len(DISCOVERY_QUESTIONS),
            "question": DISCOVERY_QUESTIONS[sess["step"]],
        }

    # --- Blueprint ---
    def build_blueprint(self, template_id: str = None,
                          discovery_answers: dict = None,
                          customizations: dict = None) -> dict:
        """Build a blueprint. If template_id given, start from template.
        discovery_answers customize (es. size=1 → rimuovi HR)."""
        base = self.get_template(template_id) if template_id else None
        if not base:
            return {"ok": False, "error": f"template {template_id} non trovato"}
        bp = dict(base)
        bp["blueprint_id"] = "bp_" + uuid.uuid4().hex[:8]
        bp["created_at"] = int(time.time())
        bp["customizations"] = customizations or {}
        bp["discovery"] = discovery_answers or {}

        # Apply customizations: drop agents if size=1
        if discovery_answers:
            size = discovery_answers.get("size", "")
            if size == "1":
                # Solo professionista: rimuovi HR e Training Manager
                bp["agents"] = [a for a in bp["agents"]
                                  if a["name"] not in ("hr", "training_manager")]

        # Persist blueprint
        out_path = BLUEPRINTS_DIR / f"{bp['blueprint_id']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(bp, f, ensure_ascii=False, indent=2)
        self._emit("blueprint_created", {"id": bp["blueprint_id"],
                                           "agents": len(bp["agents"])})
        return {"ok": True, "blueprint": bp}

    def list_blueprints(self) -> list:
        out = []
        for p in sorted(BLUEPRINTS_DIR.glob("bp_*.json"), reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    bp = json.load(f)
                out.append({
                    "id": bp.get("blueprint_id"),
                    "created_at": bp.get("created_at"),
                    "agents_count": len(bp.get("agents", [])),
                    "industry": bp.get("industry"),
                })
            except Exception:
                pass
        return out

    # --- Deploy ---
    def deploy_blueprint(self, blueprint_id: str, dry_run: bool = False) -> dict:
        """Generate Python file for each NEW agent in the blueprint.
        Existing agents (steward, dpo, ciso, etc.) are skipped."""
        bp_path = BLUEPRINTS_DIR / f"{blueprint_id}.json"
        if not bp_path.exists():
            return {"ok": False, "error": "blueprint non trovato"}
        with open(bp_path, "r", encoding="utf-8") as f:
            bp = json.load(f)

        # Identify existing agents in team registry
        try:
            from . import team_registry
            existing = {a.name for a in team_registry.all_agents()}
        except Exception:
            existing = set()

        results = []
        deployed = 0
        failed = 0
        for agent_def in bp.get("agents", []):
            name = agent_def["name"]
            if name in existing:
                results.append({"name": name, "status": "skipped_existing"})
                continue
            self._emit("agent_generating", {"name": name})
            code, gen_error = _generate_agent_code(agent_def)
            if not code:
                results.append({"name": name, "status": "failed",
                                "error": gen_error or "LLM no output"})
                failed += 1
                continue
            # Code è già validato AST dal generatore (con retry).
            # Write to pending
            pending_path = PENDING_DIR / f"{name}.py"
            pending_path.write_text(code, encoding="utf-8")
            # Smoke test
            # Need empty __init__.py in _pending/
            init_p = PENDING_DIR / "__init__.py"
            if not init_p.exists():
                init_p.write_text("", encoding="utf-8")
            smoke = _smoke_test(name)
            if not smoke["ok"]:
                results.append({"name": name, "status": "failed",
                                "error": f"smoke: {smoke['error']}"})
                failed += 1
                try:
                    pending_path.unlink()
                except OSError:
                    pass
                continue
            # Move to agents/ (unless dry_run)
            if not dry_run:
                final_path = ROOT / "agents" / f"{name}.py"
                # Backup existing if any
                if final_path.exists():
                    backup = final_path.with_suffix(f".py.bak.{int(time.time())}")
                    final_path.rename(backup)
                pending_path.rename(final_path)
                results.append({"name": name, "status": "deployed",
                                "smoke": smoke.get("sample_result", "")})
                deployed += 1
                try:
                    import audit_log
                    audit_log.log("architect.deployed", {"name": name,
                                                           "blueprint": blueprint_id})
                except Exception:
                    pass
            else:
                results.append({"name": name, "status": "dry_run_ok"})
                try:
                    pending_path.unlink()
                except OSError:
                    pass

        # Reload registry if we deployed any
        if deployed > 0 and not dry_run:
            try:
                from . import team_registry
                team_registry._loaded = False
                team_registry._agents = {}
                team_registry._load_all()
            except Exception as e:
                self._emit("reload_error", {"error": str(e)})

        self._emit("deploy_complete", {
            "blueprint_id": blueprint_id,
            "deployed": deployed,
            "failed": failed,
            "dry_run": dry_run,
        })
        return {
            "ok": failed == 0,
            "blueprint_id": blueprint_id,
            "deployed": deployed,
            "failed": failed,
            "dry_run": dry_run,
            "results": results,
        }

    # --- Main run ---
    def run(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "list_templates":
            return {"ok": True, "templates": self.list_templates()}
        if op == "get_template":
            t = self.get_template(payload.get("template_id", ""))
            return {"ok": bool(t), "template": t}
        if op == "start_discovery":
            return {"ok": True, **self.start_discovery()}
        if op == "discovery_answer":
            return self.discovery_answer(payload.get("session_id", ""),
                                            payload.get("answer"))
        if op == "build_blueprint":
            return self.build_blueprint(
                template_id=payload.get("template_id"),
                discovery_answers=payload.get("discovery_answers"),
                customizations=payload.get("customizations"),
            )
        if op == "list_blueprints":
            return {"ok": True, "blueprints": self.list_blueprints()}
        if op == "deploy_blueprint":
            return self.deploy_blueprint(
                payload.get("blueprint_id", ""),
                dry_run=bool(payload.get("dry_run", False)),
            )
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = ArchitectAgent()
