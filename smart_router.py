"""Router intelligente Haiku-based.

Strategy:
  1. Set base "core" di tool sempre presenti (~15 essenziali)
  2. Haiku riceve la query + lista categorie disponibili e ritorna 1-3 categorie
  3. Aggiungiamo i tool di quelle categorie al core
  4. Cache stabile: per query simili → stesso subset → cache hit

Costo Haiku per classificazione: ~$0.0003 / query
vs costo evitato: ~$0.005-0.010 di tokens schema su Sonnet
ROI positivo se schema_savings > $0.0003
"""
import threading
import time as _time

# Core sempre presente (15 tool essenziali, ~600 token totali)
CORE = {
    "get_time", "calculate", "get_weather", "open_application",
    "save_note", "list_notes", "add_todo", "list_todos",
    "remember_fact", "list_facts", "system_info", "set_timer",
    "set_reminder", "show_settings", "wikipedia",
}

# Mappa categoria -> tool names
CATEGORY_MAP = {
    "email": ["list_emails", "search_emails", "read_email", "summarize_inbox", "send_email"],
    "news": ["get_news"],
    "sports": ["sports_news"],
    "weather": ["get_weather"],
    "wikipedia": ["wikipedia"],
    "music": ["list_music", "play_music_track", "stop_music_track"],
    "radio": ["play_radio"],
    "stocks": ["stock_quote"],
    "windows": ["list_windows", "focus_window", "close_window", "minimize_all"],
    "apps": ["open_application"],
    "system": ["system_info", "set_volume", "get_volume", "mute_audio",
               "set_brightness", "lock_pc", "shutdown_pc"],
    "files": ["find_files", "read_pdf"],
    "vision": ["analyze_screen", "take_screenshot"],
    "clipboard": ["read_clipboard", "write_clipboard"],
    "memory_notes": ["save_note", "list_notes", "add_todo", "list_todos",
                     "complete_todo", "remember_fact", "list_facts"],
    "todos": ["add_todo", "list_todos", "complete_todo"],
    "timers": ["timer_create", "timer_list", "timer_stop", "timer_rename",
               "timer_query", "timer_stop_all", "set_timer"],
    "reminders": ["set_reminder"],
    "automations": ["create_automation", "list_automations", "delete_automation",
                    "toggle_automation", "run_automation_now"],
    "scenes_macros": ["activate_scene", "list_scenes", "save_scene", "delete_scene",
                      "record_macro_start", "record_macro_stop", "run_macro",
                      "list_macros", "set_alias", "list_aliases"],
    "workspace": ["list_workspaces", "activate_workspace", "save_workspace"],
    "rag_docs": ["index_docs", "search_docs", "list_docs", "clear_docs_index"],
    "image_gen": ["generate_image"],
    "web_images": ["web_images"],
    "web_read": ["web_search", "read_webpage", "read_article_aloud"],
    "youtube": ["youtube_search", "youtube_play", "youtube_transcript"],
    "data_analysis": ["analyze_spreadsheet", "make_chart", "code_exec"],
    "english_tutor": ["english_tutor_start", "english_tutor_assess",
                      "english_tutor_log_error", "english_tutor_status",
                      "english_tutor_reset"],
    "calculation": ["calculate", "code_exec"],
    "settings": ["set_voice", "set_personality", "set_mode", "set_home_location",
                 "toggle_startup_music", "add_instruction", "list_instructions",
                 "remove_instruction", "show_settings"],
    "privacy": ["privacy_mode", "security_status", "set_pin", "remove_pin",
                "clear_conversation_log"],
    "communication": ["windows_notify", "send_voice_mail", "lan_url"],
    "reading": ["reading_open", "reading_continue", "reading_status", "reading_stop",
                "generate_podcast"],
    "organize": ["organize_downloads"],
    "smalltalk": [],
    "other": [],
}


_cache = {}
_cache_ttl = 1800  # 30 min — same intent -> same routing

# Keyword rules for instant (zero-latency) category detection.
# Keys are category names; values are Italian keyword fragments (lowercase).
# No API call needed — pure string matching, ~0ms.
_KEYWORD_RULES: dict[str, list[str]] = {
    "email":          ["email", "posta", "mail", "inbox", "invia", "scrivi a", "manda un"],
    "news":           ["notizie", "news", "ultime", "giornale", "titoli", "rassegna"],
    "weather":        ["meteo", "tempo", "temperatura", "pioggia", "sole", "vento",
                       "previsioni", "caldo", "freddo", "umidità"],
    "music":          ["musica", "canzone", "brano", "playlist", "riproduci", "ascolta",
                       "metti", "suona"],
    "radio":          ["radio", "stazione radio"],
    "stocks":         ["borsa", "azioni", "stock", "mercato", "prezzo di", "quotazione"],
    "sports":         ["sport", "calcio", "serie a", "champions", "partita", "gol",
                       "basket", "tennis", "formula 1", "moto gp"],
    "wikipedia":      ["wikipedia", "chi è", "cos'è", "storia di", "definizione",
                       "spiega", "cosa significa"],
    "system":         ["volume", "luminosità", "luminosita", "spegni", "blocca",
                       "riavvia", "sistema", "audio", "muto"],
    "windows":        ["finestra", "finestre", "schermo", "minimize", "chiudi tutto"],
    "apps":           ["apri", "lancia", "avvia", "apri l'app"],
    "files":          ["file", "documento", "cartella", "pdf", "cerca file", "trova"],
    "vision":         ["screenshot", "schermata", "cosa vedi", "analizza schermo"],
    "clipboard":      ["appunti", "clipboard", "copia", "incolla"],
    "timers":         ["timer", "conto alla rovescia", "minuti", "secondi"],
    "reminders":      ["ricordami", "promemoria", "ricorda", "avvisa"],
    "todos":          ["todo", "lista", "da fare", "compito", "attività"],
    "memory_notes":   ["nota", "appunto", "salvami", "ricorda che", "memorizza"],
    "image_gen":      ["genera immagine", "disegna", "crea immagine", "illustra",
                       "genera una foto", "fai un disegno"],
    "web_read":       ["cerca su", "google", "internet", "sito", "pagina web",
                       "leggi articolo", "cerca online"],
    "youtube":        ["youtube", "video di", "guarda", "cerca su youtube"],
    "data_analysis":  ["analizza", "grafico", "foglio", "excel", "dati", "calcola"],
    "calculation":    ["calcola", "quanto fa", "quant", "quanto è", "matematica"],
    "settings":       ["impostazioni", "voce", "personalità", "configurazione",
                       "cambia voce", "modalità"],
    "privacy":        ["privacy", "sicurezza", "pin", "blocca accesso"],
    "reading":        ["leggi", "lettura", "podcast", "libro"],
    "smalltalk":      ["ciao", "come stai", "buongiorno", "buonasera", "grazie",
                       "prego", "come va"],
}


def classify_categories_for(text: str) -> list:
    """Instant keyword-based category detection — zero API calls, zero latency.

    Replaces the old Haiku classify_intent call.  For most queries this is
    just as accurate and ~300 ms faster.  Falls back to ["other"] when no
    keywords match (core tools always available anyway).
    """
    key = text.lower().strip()[:200]

    # Cache still used so repeated identical queries skip even the regex scan
    now = _time.time()
    if key in _cache:
        ts, cats = _cache[key]
        if now - ts < _cache_ttl:
            return cats

    found = []
    for cat, keywords in _KEYWORD_RULES.items():
        if any(kw in key for kw in keywords):
            found.append(cat)

    cats = found if found else ["other"]
    _cache[key] = (now, cats)
    return cats


def get_tools_for(text: str, all_schemas: list) -> list:
    """Return the filtered list of schemas for this query."""
    cats = classify_categories_for(text)
    selected = set(CORE)
    for c in cats:
        selected.update(CATEGORY_MAP.get(c, []))
    return [s for s in all_schemas if s.get("name") in selected], cats
