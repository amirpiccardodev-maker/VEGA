"""Auto-extract personal facts from recent conversations.

Runs periodically in background: takes last N un-processed exchanges, asks
Claude (briefly + cheap) to extract NEW facts about Amir, adds them to memory.
Respects privacy mode (skipped entirely).
"""
import json
import threading
import time as _time

import memory
import security


# How often to attempt extraction (in seconds)
EXTRACT_INTERVAL_SEC = 1800  # 30 min
# Minimum new exchanges before running
MIN_NEW_EXCHANGES = 6
# Max exchanges to send to Claude
MAX_EXCHANGES_TO_SEND = 20


_last_processed_index = 0
_lock = threading.Lock()


def _get_last_processed():
    return memory.get_all().get("fact_extractor_last_idx", 0)


def _set_last_processed(idx):
    def m(d):
        d["fact_extractor_last_idx"] = idx
    memory.update(m)


def _existing_facts_set():
    return set(f["text"].lower().strip() for f in memory.get_facts())


def extract_now():
    """Run a single extraction pass."""
    if security.is_privacy_mode():
        return  # respect privacy

    with _lock:
        log = memory.get_all().get("conversation_log", [])
        last_idx = _get_last_processed()
        new_exchanges = log[last_idx:]
        if len(new_exchanges) < MIN_NEW_EXCHANGES:
            return

        # Take only the most recent batch to save tokens
        batch = new_exchanges[-MAX_EXCHANGES_TO_SEND:]

        # Build a compact transcript
        transcript_lines = []
        for ex in batch:
            transcript_lines.append(f"AMIR: {ex.get('user','')[:200]}")
            transcript_lines.append(f"VEGA: {ex.get('assistant','')[:200]}")
        transcript = "\n".join(transcript_lines)

        # Use FAST model (Haiku) for extraction - 3x cheaper, sufficient quality
        from anthropic import Anthropic
        from config import ANTHROPIC_API_KEY, MODEL_FAST
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        existing = list(_existing_facts_set())
        existing_str = "\n".join(f"- {f}" for f in existing[:30]) if existing else "(nessuno)"

        prompt = f"""Analizza il seguente estratto di conversazione tra Amir e Vega.
Estrai SOLO nuovi fatti DURATURI su Amir che non sono gia' nella lista esistente.
Esempi di fatti validi: preferenze, abitudini, lavoro, famiglia, hobby, allergie, luoghi importanti.
NON estrarre: domande momentanee, comandi tecnici, generic info.
Rispondi SOLO con un JSON array di stringhe (max 5 fatti, in italiano), o array vuoto.

FATTI GIA' MEMORIZZATI:
{existing_str}

CONVERSAZIONE:
{transcript}

Rispondi solo con JSON valido tipo: ["fatto 1", "fatto 2"]"""

        try:
            response = client.messages.create(
                model=MODEL_FAST,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            # Strip markdown fences if any
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            facts = json.loads(text)
            if not isinstance(facts, list):
                facts = []
        except Exception as e:
            print(f"[fact_extractor] {e}")
            facts = []

        # Add facts (dedup)
        existing_set = _existing_facts_set()
        added = 0
        for f in facts:
            if not isinstance(f, str):
                continue
            f = f.strip()
            if not f or len(f) < 10:
                continue
            if f.lower() in existing_set:
                continue
            memory.add_fact(f)
            existing_set.add(f.lower())
            added += 1

        _set_last_processed(len(log))
        return added


def background_loop(stop_event):
    """Run extraction every EXTRACT_INTERVAL_SEC."""
    while not stop_event.is_set():
        try:
            extract_now()
        except Exception as e:
            print(f"[fact_extractor] loop error: {e}")
        # Sleep in small increments so we respond to stop quickly
        for _ in range(EXTRACT_INTERVAL_SEC):
            if stop_event.is_set():
                return
            _time.sleep(1)
