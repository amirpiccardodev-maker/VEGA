"""Privacy DPO Agent — GDPR Art. 5/6/25/30/32/33/35.

NOTE LEGALE: questo agente è un ASSISTENTE OPERATIVO. Il DPO formale
(Art. 37 GDPR) deve essere una persona fisica. L'utente resta titolare.
"""
import json
import time
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
GDPR_REGISTER_FILE = ROOT / "data" / "gdpr_register.json"
GDPR_REGISTER_FILE.parent.mkdir(parents=True, exist_ok=True)


DPO_SYSTEM = """Sei il DPO (Data Protection Officer) ASSISTENTE operativo allineato
a GDPR (Reg. UE 2016/679) + provvedimenti del Garante Privacy italiano.

Per ogni operazione richiesta, valuta:
- Art. 5: liceità, minimizzazione, finalità, esattezza, conservazione, integrità, accountability
- Art. 6: base giuridica (consenso/contratto/obbligo/interesse legittimo)
- Art. 25: privacy by design & by default
- Art. 32: misure di sicurezza adeguate
- Art. 33-34: data breach (notifica entro 72h)
- Art. 35: DPIA per trattamenti ad alto rischio

Output SOLO JSON:
{
  "verdict": "allow" | "allow_with_conditions" | "deny" | "escalate",
  "basis_juridique": "art_6_1_<a|b|c|d|e|f>",
  "conditions": ["..."],
  "rationale": "1-2 frasi italiane",
  "score": 0.0..1.0
}
"""


# Tool che richiedono preflight DPO (toccano dati personali o terzi)
SENSITIVE_TOOLS = {
    "send_email", "send_draft", "compose_draft", "reply_draft",
    "list_emails", "summarize_inbox",
    "save_note", "remember_fact", "add_todo",
    "browse_url", "web_search",
    "windows_notify",
}


def _load_register() -> dict:
    if not GDPR_REGISTER_FILE.exists():
        return {"version": "1.0", "treatments": []}
    try:
        with open(GDPR_REGISTER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": "1.0", "treatments": []}


def _save_register(d: dict):
    with open(GDPR_REGISTER_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _ensure_default_treatments():
    """Registra al primo avvio i trattamenti di base di Vega."""
    reg = _load_register()
    if reg["treatments"]:
        return
    reg["treatments"] = [
        {
            "id": "treat_default_001",
            "name": "Conversazione utente con assistente",
            "purpose": "Erogazione servizio assistente personale",
            "base_juridique": "art_6_1_b_contract",
            "data_categories": ["voice", "transcribed_text", "extracted_facts"],
            "data_subjects": ["controller_himself"],
            "retention_period": "indefinite_until_user_deletion",
            "international_transfers": "none",
            "security_measures": [
                "PIN-gated sensitive actions",
                "Bearer auth + rate limit",
                "Mem0 user_id namespacing",
                "Audit log hash-chained",
                "TLS opt-in",
                "Output filter + honeypot canaries"
            ],
            "created_at": int(time.time()),
            "dpia_required": False,
        },
        {
            "id": "treat_default_002",
            "name": "Memoria episodica via Mem0",
            "purpose": "Personalizzazione assistente nel tempo",
            "base_juridique": "art_6_1_a_consent",
            "data_categories": ["conversation_facts", "preferences"],
            "data_subjects": ["controller_himself"],
            "retention_period": "until_user_deletion",
            "international_transfers": "none",
            "security_measures": ["Local Chroma storage", "no cloud sync"],
            "created_at": int(time.time()),
            "dpia_required": False,
        },
    ]
    _save_register(reg)


class DPOAgent(TeamAgent):
    name = "dpo"
    tier = 1
    icon = "🔐"
    description = "Privacy DPO — preflight tool + registro Art. 30 + DPIA"
    model_pref = "haiku"

    def __init__(self):
        super().__init__()
        _ensure_default_treatments()

    def preflight(self, tool_name: str, args: dict) -> dict:
        """Valuta un tool call prima dell'esecuzione. Cached per (tool, args_hash)."""
        if tool_name not in SENSITIVE_TOOLS:
            return {"verdict": "allow", "basis_juridique": "n/a",
                    "rationale": "tool non sensibile", "score": 1.0,
                    "conditions": []}
        # Build a compact context for LLM
        ctx = {
            "tool": tool_name,
            "args_summary": str(args)[:400] if args else "",
            "active_treatments": [t["id"] for t in _load_register().get("treatments", [])][:5],
        }
        prompt = f"{DPO_SYSTEM}\n\nContesto: {json.dumps(ctx, ensure_ascii=False)}\n\nJSON:"
        result = self.call_haiku_json(prompt)
        if not result or "verdict" not in result:
            # Fail-open con score basso, log warning
            self._emit("preflight_fallback", {"tool": tool_name})
            return {"verdict": "allow", "basis_juridique": "fallback",
                    "rationale": "LLM unavailable, fail-open with audit",
                    "score": 0.3, "conditions": []}
        result.setdefault("conditions", [])
        result.setdefault("score", 0.7)
        self._emit("preflight", {
            "tool": tool_name,
            "verdict": result["verdict"],
            "rationale": result.get("rationale", "")[:200],
        })
        try:
            import audit_log
            audit_log.log("dpo.preflight", {
                "tool": tool_name, "verdict": result["verdict"],
                "basis": result.get("basis_juridique"),
            })
        except Exception:
            pass
        return result

    def register_treatment(self, treatment: dict) -> str:
        """Aggiunge un trattamento al registro Art. 30."""
        reg = _load_register()
        tid = f"treat_{int(time.time())}"
        treatment["id"] = tid
        treatment["created_at"] = int(time.time())
        reg.setdefault("treatments", []).append(treatment)
        _save_register(reg)
        self._emit("treatment_registered", {"id": tid,
                                              "name": treatment.get("name")})
        return tid

    def get_register(self) -> dict:
        return _load_register()

    def run(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "preflight":
            return self.preflight(payload.get("tool", ""), payload.get("args", {}))
        if op == "register":
            tid = self.register_treatment(payload.get("treatment", {}))
            return {"ok": True, "treatment_id": tid}
        if op == "get_register":
            return {"ok": True, "register": self.get_register()}
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = DPOAgent()
