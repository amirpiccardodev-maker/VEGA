"""English tutor adattivo.

Mantiene un profilo dell'utente: livello (A1-C2), argomenti di interesse,
errori frequenti. Propone sessioni di esercizio parlato/scritto.

Sessioni:
  - 'conversation': chiacchierata in inglese di N minuti, con correzione
  - 'translate': traduce frasi italiane proposte
  - 'grammar': mini-esercizi su un argomento grammaticale
  - 'vocabulary': nuove parole su topic specifico
  - 'pronunciation': frasi da ripetere
  - 'free': sessione libera, lui ti propone

Gli esercizi sono GUIDATI: il TUTOR (Claude) ti propone, valuta, suggerisce.
Tutto via voce - Vega parla inglese, tu rispondi.
"""
import json
from pathlib import Path
from datetime import datetime

import memory


PROFILE_KEY = "english_tutor_profile"


def _profile():
    return memory.get_all().get(PROFILE_KEY, {
        "level": None,
        "topics_of_interest": [],
        "frequent_errors": [],
        "sessions": [],
        "last_session": None,
        "lessons_completed": 0,
    })


def _save_profile(p):
    def m(d):
        d[PROFILE_KEY] = p
    memory.update(m)


TOOLS = [
    {"name": "english_tutor_start",
     "description": "Avvia una sessione di apprendimento inglese. Tipi: 'conversation' (chiacchierata), 'translate' (traduzione), 'grammar' (grammatica), 'vocabulary' (vocabolario), 'pronunciation' (pronuncia), 'free' (libera). Usalo quando l'utente chiede di esercitarsi con l'inglese.",
     "input_schema": {"type": "object", "properties": {
         "session_type": {"type": "string", "enum": ["conversation", "translate", "grammar", "vocabulary", "pronunciation", "free"]},
         "topic": {"type": "string", "description": "Argomento specifico (es. lavoro, viaggi, cibo)"},
     }, "required": ["session_type"]}},
    {"name": "english_tutor_assess",
     "description": "Valuta il livello di inglese dell'utente facendo poche domande mirate. Aggiorna il profilo.",
     "input_schema": {"type": "object", "properties": {
         "level": {"type": "string", "enum": ["A1", "A2", "B1", "B2", "C1", "C2"]},
         "notes": {"type": "string", "description": "Note sui punti di forza/debolezza osservati"},
     }, "required": ["level"]}},
    {"name": "english_tutor_log_error",
     "description": "Registra un errore tipico dell'utente per usarlo nelle prossime sessioni.",
     "input_schema": {"type": "object", "properties": {
         "error": {"type": "string", "description": "Es. 'usa pp invece di pp con verbi irregolari'"},
         "example": {"type": "string"},
     }, "required": ["error"]}},
    {"name": "english_tutor_status",
     "description": "Mostra il profilo dell'utente: livello, sessioni fatte, errori frequenti.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "english_tutor_reset",
     "description": "Resetta completamente il profilo English tutor.",
     "input_schema": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": ["confirm"]}},
]


SESSION_TEMPLATES = {
    "conversation": (
        "AVVIA UNA SESSIONE DI CONVERSAZIONE IN INGLESE. Parla SOLO in inglese, "
        "con un livello adatto a {level}. Topic: {topic}. "
        "Inizia con una domanda aperta e divertente. Quando Amir risponde "
        "(probabilmente in inglese, magari con errori), correggi delicatamente "
        "i suoi sbagli e proponi la prossima domanda. Una correzione alla volta. "
        "Non essere pedante. Dura 5-10 minuti."
    ),
    "translate": (
        "Esercizio di TRADUZIONE. Proponi ad Amir 3 frasi italiane di livello {level} "
        "(una facile, una media, una difficile) sul tema '{topic}'. "
        "Chiedigli di tradurle in inglese. Una alla volta. Correggi e spiega gli "
        "errori. Parla principalmente in italiano per le spiegazioni."
    ),
    "grammar": (
        "Esercizio di GRAMMATICA per livello {level} sul tema '{topic}'. "
        "Spiega in italiano una regola, poi proponi 3-5 frasi da completare. "
        "Aspetta la risposta di Amir, correggi, vai al prossimo. "
        "Esempi: present perfect vs simple past, modal verbs, conditionals, ecc."
    ),
    "vocabulary": (
        "Lezione di VOCABOLARIO inglese su '{topic}' livello {level}. "
        "Proponi 5-7 parole nuove con esempi d'uso. "
        "Chiedi ad Amir di costruire una frase con ognuna. "
        "Correggi a voce."
    ),
    "pronunciation": (
        "Esercizio di PRONUNCIA INGLESE. Proponi 5-8 parole tipiche difficili per italiani "
        "(es. words ending in -ed, 'th', 'rural', 'thoroughly'). "
        "Per ognuna, ripeti tu prima, poi chiedi ad Amir di ripeterla. "
        "Indica gli errori probabili e dai consigli articolatori."
    ),
    "free": (
        "Avvia una sessione di apprendimento LIBERA. Chiedi prima ad Amir cosa "
        "vuole praticare oggi (parlato, scritto, grammatica, vocabolario) e su "
        "che tema. Poi adattati. Sii incoraggiante."
    ),
}


def run(name, args):
    p = _profile()

    if name == "english_tutor_start":
        st = args.get("session_type", "free")
        topic = args.get("topic", "argomenti generali")
        if not p.get("level"):
            return ("Prima dimmi il tuo livello attuale di inglese (A1 principiante - C2 madrelingua). "
                    "Posso anche valutarlo io facendoti qualche domanda - di' 'valuta il mio livello'.")
        level = p["level"]
        template = SESSION_TEMPLATES.get(st, SESSION_TEMPLATES["free"])
        instruction = template.format(level=level, topic=topic)
        # Track session start
        p["last_session"] = datetime.now().isoformat()
        p.setdefault("sessions", []).append({
            "type": st, "topic": topic, "started": p["last_session"],
        })
        p["sessions"] = p["sessions"][-50:]
        p["lessons_completed"] = p.get("lessons_completed", 0) + 1
        _save_profile(p)

        errors_note = ""
        if p.get("frequent_errors"):
            recent_errors = p["frequent_errors"][-5:]
            errors_note = ("\n\nERRORI TIPICI DI AMIR (correggi quando li ripete):\n" +
                           "\n".join(f"- {e}" for e in recent_errors))

        return ("[INIZIA SESSIONE INGLESE - segui queste istruzioni come tutor]\n"
                f"{instruction}{errors_note}\n\nInizia ORA, parla a Amir come un tutor di lingua paziente.")

    if name == "english_tutor_assess":
        lvl = args.get("level", "")
        notes = args.get("notes", "")
        p["level"] = lvl
        if notes:
            p.setdefault("notes_history", []).append({"ts": datetime.now().isoformat(), "notes": notes})
        _save_profile(p)
        return f"Livello inglese impostato: {lvl}. Note salvate."

    if name == "english_tutor_log_error":
        err = args.get("error", "")
        ex = args.get("example", "")
        line = err + (f" (es: {ex})" if ex else "")
        p.setdefault("frequent_errors", []).append(line)
        p["frequent_errors"] = p["frequent_errors"][-30:]
        _save_profile(p)
        return f"Registrato: {line}"

    if name == "english_tutor_status":
        lvl = p.get("level") or "non ancora valutato"
        sessions = len(p.get("sessions", []))
        last = p.get("last_session", "mai")
        if last != "mai":
            try:
                last = datetime.fromisoformat(last).strftime("%d/%m %H:%M")
            except Exception:
                pass
        errors = p.get("frequent_errors", [])
        out = [
            f"Livello: {lvl}",
            f"Lezioni totali: {p.get('lessons_completed', 0)}",
            f"Ultima sessione: {last}",
            f"Errori ricorrenti: {len(errors)}",
        ]
        if errors:
            out.append("Ultimi errori rilevati:")
            for e in errors[-5:]:
                out.append(f"  - {e}")
        return "\n".join(out)

    if name == "english_tutor_reset":
        if not args.get("confirm"):
            return "Per confermare di' 'conferma reset tutor inglese'."
        def m(d):
            d[PROFILE_KEY] = {
                "level": None, "topics_of_interest": [], "frequent_errors": [],
                "sessions": [], "last_session": None, "lessons_completed": 0,
            }
        memory.update(m)
        return "Profilo tutor inglese azzerato."

    return "?"
