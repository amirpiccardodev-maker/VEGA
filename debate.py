"""Multi-agent debate: 3 ruoli ragionano in parallelo + sintesi.

Filosofia: per decisioni complesse, una singola call LLM ha bias. Tre
prospettive forzate in parallelo (Haiku, cheap) + sintesi Sonnet danno
risposte più equilibrate.

API:
    run(question, on_event=None) -> {"perspectives": [...], "synthesis": "..."}
"""
import concurrent.futures as _cf
import time

import bus
import fast_brain


ROLES = [
    {
        "name": "ottimista",
        "icon": "☀️",
        "system": (
            "Sei l'OTTIMISTA. Analizza il problema cercando opportunità, vantaggi "
            "e scenari positivi. Sii concreto, evita banalità da motivatore. "
            "Max 4 frasi italiane."
        ),
    },
    {
        "name": "pessimista",
        "icon": "⚠️",
        "system": (
            "Sei il PESSIMISTA costruttivo. Individua rischi, costi nascosti, "
            "trade-off ignorati, what-could-go-wrong. Concreto, non lamentoso. "
            "Max 4 frasi italiane."
        ),
    },
    {
        "name": "pragmatico",
        "icon": "🛠️",
        "system": (
            "Sei il PRAGMATICO. Indica i passi operativi concreti: cosa fare, "
            "in quale ordine, quanto tempo serve, quale è la prima azione "
            "minima viabile. Max 4 frasi italiane."
        ),
    },
]


def _one_perspective(role: dict, question: str) -> dict:
    """Chiama Haiku per una singola prospettiva."""
    prompt = f"{role['system']}\n\nDomanda dell'utente: {question}\n\nLa tua risposta:"
    started = time.time()
    try:
        text = fast_brain.fast_call(prompt) or ""
    except Exception as e:
        text = f"(errore: {e})"
    return {
        "role": role["name"],
        "icon": role["icon"],
        "text": text.strip(),
        "duration_sec": round(time.time() - started, 1),
    }


SYNTHESIS_SYSTEM = (
    "Hai ricevuto 3 prospettive (ottimista, pessimista, pragmatico) sulla domanda "
    "di un utente. Sintetizza in italiano (max 6 frasi) la migliore risposta "
    "complessiva: prendi il meglio di ciascuna prospettiva, segnala i trade-off, "
    "e finisci con UN consiglio concreto. Tono diretto, da consulente esperto. "
    "Non ripetere meccanicamente i 3 punti di vista."
)


def _synthesize(question: str, perspectives: list) -> str:
    """Sintesi finale tramite Sonnet (via Brain) per qualità più alta."""
    parts = "\n\n".join(
        f"### {p['icon']} {p['role'].upper()}\n{p['text']}"
        for p in perspectives
    )
    prompt = (
        f"{SYNTHESIS_SYSTEM}\n\n"
        f"DOMANDA: {question}\n\n"
        f"PROSPETTIVE:\n{parts}\n\n"
        f"SINTESI:"
    )
    # Usa Haiku per economia: la sintesi è già grounded sulle 3 prospettive.
    try:
        return (fast_brain.fast_call(prompt) or "").strip()
    except Exception as e:
        return f"(errore sintesi: {e})"


def run(question: str, on_event=None) -> dict:
    """Run a 3-perspective debate. Returns dict with perspectives + synthesis."""
    started = time.time()
    if on_event:
        on_event("started", {"question": question})
    bus.publish("debate.started", {"question": question[:200]})

    perspectives = [None, None, None]
    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(_one_perspective, r, question): i
                for i, r in enumerate(ROLES)}
        for fut in _cf.as_completed(futs):
            i = futs[fut]
            try:
                perspectives[i] = fut.result()
            except Exception as e:
                perspectives[i] = {"role": ROLES[i]["name"], "icon": ROLES[i]["icon"],
                                   "text": f"(errore: {e})", "duration_sec": 0}
            if on_event:
                on_event("perspective", perspectives[i])

    synthesis = _synthesize(question, perspectives)
    duration = round(time.time() - started, 1)
    result = {
        "question": question,
        "perspectives": perspectives,
        "synthesis": synthesis,
        "duration_sec": duration,
    }
    if on_event:
        on_event("finished", result)
    bus.publish("debate.finished", {"duration": duration})
    return result


# ============ Detection in user input ============
_DEBATE_TRIGGERS = (
    "dibattito su ", "dibatti su ", "fai un dibattito ",
    "analisi a 360 ", "pro e contro di ", "vale la pena ",
    "dovrei ", "conviene ",
)


def detect_debate(text: str) -> str:
    """If text triggers a debate, return the question; else empty string."""
    if not text:
        return ""
    t = text.strip().lower()
    for trig in _DEBATE_TRIGGERS:
        if t.startswith(trig):
            return text.strip()[len(trig):].strip(" :,.;?") or text.strip()
    return ""
