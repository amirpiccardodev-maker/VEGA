"""Email compose+draft tools: prepara bozze senza inviare, oppure
genera una bozza di risposta via Haiku dato un email originale."""
import json
import os
import time
from pathlib import Path

import fast_brain


DRAFTS_DIR = Path(__file__).parent.parent / "data" / "email_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


TOOLS = [
    {
        "name": "compose_draft",
        "description": (
            "Crea una bozza email salvata localmente (NON la invia). "
            "Usalo quando l'utente dice 'prepara una mail per X', "
            "'componi una bozza', 'fai una bozza di risposta'. "
            "Restituisce l'ID bozza; per inviare poi servirà send_draft."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "topic": {"type": "string",
                          "description": "Se body manca, descrivi cosa scrivere e Haiku la genererà."},
                "tone": {"type": "string", "description": "Tono: formale | informale | cordiale | diretto. Default: cordiale."},
            },
            "required": ["to"],
        },
    },
    {
        "name": "reply_draft",
        "description": (
            "Genera una bozza di risposta a un'email ricevuta. "
            "Passagli il testo originale e l'intento della tua risposta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "original_text": {"type": "string"},
                "from_addr": {"type": "string"},
                "intent": {"type": "string", "description": "Cosa vuoi rispondere (in italiano libero)."},
                "tone": {"type": "string"},
            },
            "required": ["original_text", "intent"],
        },
    },
    {
        "name": "send_draft",
        "description": "Invia una bozza precedentemente creata via compose_draft o reply_draft.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },
    {
        "name": "list_drafts",
        "description": "Lista le bozze email salvate non ancora inviate.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _save_draft(d: dict) -> str:
    did = "dr_" + str(int(time.time() * 1000))
    d["id"] = did
    d["created_at"] = int(time.time())
    with open(DRAFTS_DIR / f"{did}.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return did


def _load_draft(did: str) -> dict:
    p = DRAFTS_DIR / f"{did}.json"
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _generate_body(topic: str, tone: str = "cordiale", to: str = "") -> str:
    """Use Haiku to generate body from a topic description."""
    prompt = (
        f"Sei un assistente che scrive email professionali in italiano. "
        f"Tono richiesto: {tone}. Destinatario: {to or 'sconosciuto'}.\n\n"
        f"Devi scrivere il corpo dell'email per questo intento:\n{topic}\n\n"
        f"Scrivi SOLO il body (senza saluto generico 'Caro X' a meno che il "
        f"destinatario sia noto). Max 8 righe. Inizia direttamente con il "
        f"contenuto. Niente preamboli tipo 'Ecco la bozza'."
    )
    return (fast_brain.fast_call(prompt) or "").strip()


def _generate_reply(original: str, intent: str, tone: str = "cordiale") -> str:
    prompt = (
        f"Sei un assistente che scrive risposte email in italiano. "
        f"Tono: {tone}.\n\n"
        f"EMAIL ORIGINALE RICEVUTA:\n{original[:2000]}\n\n"
        f"INTENTO DELLA TUA RISPOSTA:\n{intent}\n\n"
        f"Scrivi SOLO il corpo della risposta, max 8 righe, in italiano. "
        f"Niente preamboli."
    )
    return (fast_brain.fast_call(prompt) or "").strip()


def run(name, args):
    args = args or {}
    if name == "compose_draft":
        to = args.get("to", "").strip()
        subject = args.get("subject", "").strip() or "(senza oggetto)"
        body = args.get("body", "").strip()
        topic = args.get("topic", "").strip()
        tone = args.get("tone", "cordiale")
        if not body and topic:
            body = _generate_body(topic, tone, to)
        if not body:
            return "Servono body oppure topic."
        did = _save_draft({"to": to, "subject": subject, "body": body, "tone": tone})
        return (f"Bozza creata (id: {did}).\n\n"
                f"To: {to}\nSubject: {subject}\n\n{body}\n\n"
                f"Per inviare: usa send_draft con draft_id={did}.")

    if name == "reply_draft":
        original = args.get("original_text", "")
        intent = args.get("intent", "")
        if not (original and intent):
            return "Servono original_text e intent."
        body = _generate_reply(original, intent, args.get("tone", "cordiale"))
        did = _save_draft({
            "to": args.get("from_addr", ""),
            "subject": "Re: ...",
            "body": body, "in_reply_to": original[:200],
        })
        return f"Bozza risposta creata (id: {did}).\n\n{body}\n\nPer inviare: send_draft({did})."

    if name == "send_draft":
        did = args.get("draft_id", "").strip()
        d = _load_draft(did)
        if not d:
            return f"Bozza {did} non trovata."
        # Reuse send_email tool
        try:
            from tools import email_send
            r = email_send.run("send_email", {
                "to": d["to"], "subject": d["subject"], "body": d["body"],
            })
            # Move to sent/
            try:
                os.unlink(DRAFTS_DIR / f"{did}.json")
            except OSError:
                pass
            return f"Inviata: {r}"
        except Exception as e:
            return f"Errore invio: {e}"

    if name == "list_drafts":
        items = []
        for p in sorted(DRAFTS_DIR.glob("dr_*.json"), reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                items.append(f"- {d['id']}: {d.get('to','?')} | {d.get('subject','?')[:50]}")
            except Exception:
                pass
        if not items:
            return "Nessuna bozza salvata."
        return "Bozze:\n" + "\n".join(items)

    return f"Tool sconosciuto: {name}"
