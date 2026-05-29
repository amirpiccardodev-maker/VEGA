"""Tool chaining hints — suggerisce a Claude il prossimo tool probabile.

Approccio: dopo l'esecuzione di un tool, esamina il risultato + il nome tool
e ritorna 0..2 "next_suggestions" che vengono accodate al tool_result.
Claude legge la suggestion e decide se chainare.

Esempio:
    web_search restituisce risultati con URL → suggerisce read_article_aloud
    list_emails restituisce inbox piena → suggerisce summarize_inbox
    get_weather restituisce maltempo → suggerisce reminder_create

Non forza nulla: è solo un hint testuale che Claude può ignorare.
"""

# Mappa: tool_name → [(condition_fn(result), suggestion_template)]
CHAIN_RULES = {
    "web_search": [
        (lambda r: "http" in str(r)[:2000],
         "Trovati link rilevanti. Se l'utente vuole approfondire, "
         "usa read_article_aloud su uno dei link."),
        (lambda r: len(str(r)) > 500,
         "Risultati abbondanti. Se serve sintesi, considera di filtrare i top 3."),
    ],
    "list_emails": [
        (lambda r: True,
         "Inbox letta. Se l'utente vuole un riassunto, usa summarize_inbox. "
         "Se vuole rispondere a una mail, usa reply_draft."),
    ],
    "get_news": [
        (lambda r: True,
         "Notizie scaricate. Se servono dettagli su una specifica notizia, "
         "usa read_article_aloud con il link."),
    ],
    "wikipedia": [
        (lambda r: True,
         "Articolo Wikipedia letto. Se serve un'immagine del soggetto, "
         "usa web_images. Per più contesto storico, fai una web_search."),
    ],
    "analyze_screen": [
        (lambda r: True,
         "Screen analizzato. Se l'utente vuole agire su quello che vedi "
         "(es. cliccare, riempire form), considera browse_url o computer use."),
    ],
    "get_weather": [
        (lambda r: any(w in str(r).lower() for w in ("pioggia", "temporale", "neve", "tempesta")),
         "Maltempo previsto. Considera di proporre un reminder per l'utente."),
    ],
    "ask_recent_news": [
        (lambda r: "Nessuna" in str(r)[:50],
         "Nessuna news nell'indice locale. Considera get_news per fetch live."),
    ],
    "memory_search": [
        (lambda r: "Nessun risultato" in str(r)[:100],
         "Memoria vuota su questo. Suggerisci all'utente di farti memorizzare "
         "qualcosa con remember_fact."),
    ],
    "compose_draft": [
        (lambda r: True,
         "Bozza creata. NON inviare senza esplicita conferma utente. "
         "Mostra la bozza prima."),
    ],
    "generate_image": [
        (lambda r: True,
         "Immagine generata. Se l'utente vuole varianti, ri-chiama "
         "generate_image con prompt leggermente modificato."),
    ],
}


def hints_for(tool_name: str, result) -> list:
    """Return 0..2 suggestion strings for the given tool result."""
    rules = CHAIN_RULES.get(tool_name)
    if not rules:
        return []
    out = []
    for cond, suggestion in rules:
        try:
            if cond(result):
                out.append(suggestion)
                if len(out) >= 2:
                    break
        except Exception:
            continue
    return out


def annotate(tool_name: str, result):
    """Append chain hints to a tool result.

    If result is a string: append as text.
    If result is a list (blocks): append a text block.
    """
    hints = hints_for(tool_name, result)
    if not hints:
        return result
    hint_text = "\n\n[CHAIN HINTS — suggerimenti per next action]\n" + \
                 "\n".join(f"• {h}" for h in hints)
    if isinstance(result, str):
        return result + hint_text
    if isinstance(result, list):
        return result + [{"type": "text", "text": hint_text}]
    return result  # unknown type, pass-through
