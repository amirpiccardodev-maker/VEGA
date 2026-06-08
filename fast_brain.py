"""Fast model helper: chiamate veloci e a basso costo via Haiku.

Usato per:
  - Intent classification / routing
  - Summarization conversazioni vecchie
  - Fact extraction (era Sonnet, ora Haiku = 1/10 costo)
  - Quick acknowledgments / yes-no questions
  - Json schema extraction from text

Costo Haiku 4.5 (stima):
  Input:  $1/M tokens
  Output: $5/M tokens
vs Sonnet:
  Input:  $3/M tokens
  Output: $15/M tokens
= circa 1/3 input, 1/3 output (3x cheaper)
"""
import json
import time
from anthropic import APIError, RateLimitError

from config import MAX_TOKENS_FAST
import memory
import llm_provider


def fast_call(prompt: str, system: str = "", max_tokens: int = None) -> str:
    """Chiamata Haiku rapida. Usa cache su system prompt se fornito."""
    mt = max_tokens or MAX_TOKENS_FAST
    sys_blocks = []
    if system:
        sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    try:
        for attempt in range(3):
            try:
                resp = llm_provider.create(
                    model=llm_provider.fast_model(),
                    max_tokens=mt,
                    system=sys_blocks if sys_blocks else "",
                    tools=[],
                    messages=[{"role": "user", "content": prompt}],
                )
                break
            except RateLimitError:
                if attempt < 2:
                    time.sleep(4)
                else:
                    raise
        # Track usage
        try:
            u = resp.usage
            memory.record_usage(
                input_tokens=getattr(u, "input_tokens", 0) or 0,
                output_tokens=getattr(u, "output_tokens", 0) or 0,
                cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
                cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
            )
        except Exception:
            pass
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text
    except Exception as e:
        return f"[fast_call error: {e}]"


def fast_json(prompt: str, schema_hint: str = "") -> dict:
    """Estrae un JSON da una risposta Haiku."""
    full = prompt
    if schema_hint:
        full += f"\n\nRispondi SOLO con JSON valido, formato: {schema_hint}"
    text = fast_call(full)
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {}


def classify_intent(user_text: str) -> dict:
    """Identifica categoria + tool consigliati. Usato dal router."""
    categories = [
        "email", "news", "weather", "wikipedia", "music", "radio",
        "stocks", "sports", "system", "windows", "apps", "files", "vision",
        "memory_notes", "todos", "timers", "reminders", "automations",
        "scenes_macros", "rag_docs", "image_gen", "web_images", "web_read",
        "youtube", "data_analysis", "english_tutor", "calculation",
        "settings", "privacy", "communication", "reading", "smalltalk", "other",
    ]
    prompt = (
        "Classifica la query utente in 1-3 categorie tra: " + ", ".join(categories) + ".\n"
        f"Query: \"{user_text}\"\n"
        "Risposta SOLO JSON: {\"categories\": [\"cat1\", \"cat2\"]}"
    )
    data = fast_json(prompt)
    cats = data.get("categories", [])
    if not isinstance(cats, list):
        cats = []
    # Filter to valid categories only
    cats = [c for c in cats if c in categories]
    return {"categories": cats or ["other"]}


def summarize_old_history(messages: list, target_summary_length: int = 150) -> str:
    """Riassumi una lista di messaggi (user+assistant alternati) in 1 paragrafo."""
    if not messages:
        return ""
    convo_text = []
    for m in messages:
        role = "AMIR" if m.get("role") == "user" else "VEGA"
        content = m.get("content")
        if isinstance(content, str):
            convo_text.append(f"{role}: {content[:200]}")
        elif isinstance(content, list):
            # Skip tool_use/tool_result for summary, use text only
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    convo_text.append(f"{role}: {b.get('text', '')[:200]}")
    if not convo_text:
        return ""
    prompt = (
        "Riassumi questa conversazione tra Amir e l'assistente Vega in un singolo "
        f"paragrafo conciso ({target_summary_length} parole max) in italiano. "
        "Mantieni i fatti importanti (chi, cosa, quando, decisioni). "
        "Non includere convenevoli ne saluti.\n\n"
        + "\n".join(convo_text)
    )
    return fast_call(prompt, max_tokens=300)
