"""Self-healing: notturno che analizza errori ricorrenti e propone fix.

Algoritmo:
  - Sottoscrive 'error.occurred' (in-memory ring buffer).
  - Ogni 24h (e una volta 30s dopo lo start per recovery rapida):
      * aggrega errori per (source, msg_fingerprint)
      * se un cluster supera MIN_OCCURRENCES, chiede a Haiku una proposta
      * salva il consiglio in memory_graph (kind=instruction)
      * emette card UI "self_healing"

Non modifica codice da solo (deliberato). L'utente vede la proposta e decide.
"""
import re
import time
import threading
from collections import defaultdict, deque

import bus


# Ring buffer in-memory (24h * picco realistico errori)
_ERRORS = deque(maxlen=2000)
_lock = threading.Lock()
_started = False

MIN_OCCURRENCES = 3
ANALYSIS_INTERVAL_SEC = 24 * 3600   # 24h
WINDOW_SEC = 24 * 3600              # analizza ultime 24h


def _fingerprint(msg: str) -> str:
    """Normalizza il messaggio per raggruppare errori 'simili'.
    Rimuove numeri, hash, path-style noise."""
    s = (msg or "").lower()
    s = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", s)
    s = re.sub(r"\d+", "<n>", s)
    s = re.sub(r"[\\/][^\s]+", "<path>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:160]


def _on_error(event):
    try:
        p = event.get("payload", {}) or {}
        src = str(p.get("source") or p.get("tool") or "unknown")[:60]
        msg = str(p.get("error") or p.get("message") or "")[:500]
        with _lock:
            _ERRORS.append({"t": time.time(), "src": src, "msg": msg,
                            "fp": _fingerprint(msg)})
    except Exception:
        pass


def _analyze_once():
    """Cluster gli errori della finestra e per ogni cluster sopra soglia
    chiedi a Haiku una proposta di mitigazione."""
    now = time.time()
    with _lock:
        recent = [e for e in _ERRORS if now - e["t"] <= WINDOW_SEC]

    if not recent:
        return

    clusters = defaultdict(list)
    for e in recent:
        clusters[(e["src"], e["fp"])].append(e)

    for (src, fp), events in clusters.items():
        if len(events) < MIN_OCCURRENCES:
            continue
        sample_msgs = list({e["msg"] for e in events})[:5]
        proposal = _ask_haiku_for_fix(src, sample_msgs, len(events))
        if not proposal:
            continue

        suggestion_text = (f"Errore ricorrente in '{src}' (visto {len(events)} volte "
                           f"nelle ultime 24h). Proposta: {proposal}")

        # Salva in memory_graph come instruction (non self-applica)
        try:
            import memory_graph as mg
            mg.add("instruction", suggestion_text, importance=0.75,
                   source="self_healing")
        except Exception:
            pass

        # Concrete diff proposal if applicable
        diff_proposal = _propose_diff_if_applicable(src, sample_msgs, len(events))

        # Emit card UI
        try:
            bus.publish("card", {
                "type": "self_healing",
                "data": {
                    "title": f"Self-healing: {src}",
                    "text": suggestion_text,
                    "samples": sample_msgs,
                    "occurrences": len(events),
                    "diff": diff_proposal,
                },
            })
        except Exception:
            pass

        bus.publish("self_healing.suggestion", {
            "source": src, "occurrences": len(events), "proposal": proposal[:200]
        })


def _ask_haiku_for_fix(source: str, sample_msgs: list, count: int) -> str:
    """Chiede a Haiku di analizzare gli errori e proporre 1 azione concreta."""
    try:
        import fast_brain
    except Exception:
        return ""
    prompt = (
        "Sei un ingegnere di affidabilità che analizza errori ricorrenti di un "
        "assistente AI personale. Proponi UNA azione concreta e specifica per "
        "mitigare il problema (max 2 frasi italiane, niente preamboli).\n\n"
        f"Componente: {source}\n"
        f"Occorrenze ultime 24h: {count}\n"
        f"Esempi di messaggi di errore:\n" +
        "\n".join(f"- {m[:200]}" for m in sample_msgs) +
        "\n\nProposta:"
    )
    try:
        out = fast_brain.fast_call(prompt)
        return (out or "").strip()
    except Exception:
        return ""


# ============ Diff proposals (propose-only, no auto-apply) ============

def _propose_diff_if_applicable(source: str, sample_msgs: list, count: int) -> dict:
    """If the error pattern matches a known config-level fixable issue,
    return a concrete diff proposal. NOT applied automatically."""
    msgs_blob = " | ".join(sample_msgs).lower()

    # Rule: ratelimit -> propose increasing backoff or model fallback
    if "rate limit" in msgs_blob or "429" in msgs_blob:
        return {
            "kind": "config_diff",
            "file": "brain.py",
            "rationale": ("Errori 'rate limit' frequenti. Suggerisco aumentare RATE_LIMIT_BACKOFF_BASE "
                          "da valore attuale a 4.0 o abilitare local_brain_enabled per offload."),
            "diff_preview": "RATE_LIMIT_BACKOFF_BASE = 4.0  # was 2.0",
        }

    # Rule: ollama timeout -> propose disable
    if "local_brain" in source and ("timeout" in msgs_blob or "connection" in msgs_blob):
        return {
            "kind": "preference",
            "file": "preferences",
            "rationale": "Local brain (Ollama) instabile. Suggerisco disabilitare local_brain_enabled.",
            "diff_preview": 'memory.set_preference("local_brain_enabled", False)',
        }

    # Rule: edge_tts errors -> propose switching to elevenlabs
    if "edge" in source.lower() or "edge_tts" in msgs_blob:
        return {
            "kind": "preference",
            "file": "preferences",
            "rationale": "Edge-TTS sembra in errore ricorrente. Switch a ElevenLabs se configurato.",
            "diff_preview": 'memory.set_preference("tts_provider", "elevenlabs")',
        }

    # Rule: whisper transcription -> upgrade model
    if "whisper" in source.lower() and "trans" in msgs_blob:
        return {
            "kind": "config_diff",
            "file": "engine.py",
            "rationale": "Whisper transcription errors. Considera 'small' invece di 'base'.",
            "diff_preview": "WhisperModel('small', device='cpu', compute_type='int8')",
        }

    return None


def _loop():
    # Prima analisi rapida dopo 30s (cattura crash precoci all'avvio)
    time.sleep(30)
    try:
        _analyze_once()
    except Exception as e:
        bus.publish("error.occurred", {"source": "self_healing", "error": str(e)})
    while True:
        time.sleep(ANALYSIS_INTERVAL_SEC)
        try:
            _analyze_once()
        except Exception as e:
            bus.publish("error.occurred", {"source": "self_healing", "error": str(e)})


def start():
    global _started
    if _started:
        return
    _started = True
    bus.subscribe("error.occurred", _on_error)
    threading.Thread(target=_loop, daemon=True, name="self_healing").start()
    bus.publish("self_healing.started", {})


def stats() -> dict:
    """Lightweight introspection for /api/diagnose-style endpoints."""
    with _lock:
        return {
            "events_buffered": len(_ERRORS),
            "started": _started,
        }
