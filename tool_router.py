"""Smart tool router.

The full tool schemas for our 58 tools amount to ~5900 tokens sent on every
Claude call. The router filters the list to tools likely relevant to the
current user message, drastically reducing input tokens.

Strategy:
  - CORE_TOOLS: ~22 tools always included (cover most general queries)
  - CATEGORY_TOOLS: extra ~30 tools only added when keywords in the message
    suggest the user wants that capability.

If no specialty category matches and the question is generic, only CORE is
sent. Typical savings: ~50% of schema tokens per call.
"""
import re

# Tools ALWAYS sent (high-frequency, general-purpose)
CORE_TOOLS = {
    "get_time",
    "calculate",
    "get_weather",
    "open_application",
    "web_search",
    "wikipedia",
    "save_note",
    "list_notes",
    "add_todo",
    "list_todos",
    "complete_todo",
    "remember_fact",
    "list_facts",
    "set_timer",
    "set_reminder",
    "system_info",
    "set_home_location",
    "show_settings",
    "add_instruction",
    "list_instructions",
    "set_volume",
    "lock_pc",
}

# Specialty tools, added only when keywords match
CATEGORY_TOOLS = {
    "email_read": {"list_emails", "search_emails", "read_email", "summarize_inbox"},
    "email_send": {"send_email"},
    "news": {"get_news"},
    "sports": {"sports_news"},
    "youtube": {"youtube_search", "youtube_play"},
    "pdf": {"read_pdf"},
    "stocks": {"stock_quote"},
    "music": {"list_music", "play_music_track", "stop_music_track"},
    "vision": {"analyze_screen", "take_screenshot"},
    "files": {"find_files"},
    "clipboard": {"read_clipboard", "write_clipboard"},
    "webpage": {"read_webpage"},
    "windows": {"list_windows", "focus_window", "close_window", "minimize_all"},
    "workspace": {"list_workspaces", "activate_workspace", "save_workspace"},
    "pc_advanced": {"set_brightness", "get_volume", "mute_audio", "shutdown_pc"},
    "self_config": {"set_voice", "set_personality", "set_mode", "toggle_startup_music",
                    "remove_instruction"},
    "docs_rag": {"index_docs", "search_docs", "list_docs", "clear_docs_index"},
    "image_gen": {"generate_image"},
    "web_images": {"web_images"},
    "travel": {"web_images", "get_weather", "wikipedia", "web_search", "read_webpage"},
}

# Keywords that trigger each category (lowercased)
CATEGORY_KEYWORDS = {
    "email_read": ["mail", "email", "posta", "inbox", "messag", "non lett"],
    "email_send": ["manda", "scrivi a", "spedisci", "invia mail", "mail a "],
    "news": ["notizi", "news", "giornal", "rassegna", "attualita", "cronaca"],
    "sports": ["sport", "partita", "calcio", "juve", "milan", "inter", "tennis", "f1", "formula"],
    "youtube": ["youtube", "video", "guarda", "metti su tube", "vedi un"],
    "pdf": ["pdf", "leggi il file", "leggi il documento", "leggi il libro"],
    "stocks": ["borsa", "azion", "titolo", "quotazion", "prezzo", "bitcoin", "crypto", "btc", "eth", "apple", "tesla", "ticker"],
    "music": ["canzon", "brano", "playlist", "ascolta", "metti musica", "metti la", "spegni musica", "stop music", "ferma musica"],
    "vision": ["guarda", "vedi", "schermo", "scherma", "screenshot", "cattur", "cosa c'e a video", "cosa vedi"],
    "files": ["trova file", "cerca file", "dove ho", "dove sta", "file chiamato"],
    "clipboard": ["appunti", "clipboard", "copi", "incoll"],
    "webpage": ["leggi pagina", "leggi sito", "questo sito", "questa pagina", "apri url", "scarica pagina"],
    "windows": ["finestr", "chiudi chrome", "chiudi edge", "minimizza", "primo piano", "porta avanti", "desktop"],
    "workspace": ["modalit", "profilo", "workspace", "lavoro", "gaming", "studio", "intrattenimento"],
    "pc_advanced": ["luminosit", "schermo piu", "schermo meno", "muta", "smut", "spegni pc", "riavvia"],
    "self_config": ["cambia voce", "cambia tono", "modalita sviluppat", "non mettere piu la musica", "personalita", "stark", "voce femmin", "voce maschil"],
    "docs_rag": ["nei miei document", "nei miei pdf", "nei miei file", "mio contratto", "mia ricetta", "appunti", "miei document",
                 "indicizz", "cerca nei", "trova nei miei", "cosa dice il", "cosa diceva il documento",
                 "rag", "miei dati personal"],
    "image_gen": ["crea immagine", "genera immagine", "genera una foto", "disegna", "crea una foto",
                  "crea un'immagine", "genera un'immagine", "immagine di",
                  "fammi un'immagine", "fai un'immagine", "render", "illustrazione",
                  "fammi un poster", "crea un poster"],
    "web_images": ["foto di", "foto del", "foto della", "mostrami foto", "mostrami le foto",
                   "immagini di", "immagini del", "mostrami immagini", "vedere foto",
                   "fammi vedere foto", "fammi vedere come", "voglio vedere", "mi mostri",
                   "com'e' fatto", "come e' fatto", "che aspetto ha"],
    "travel": ["itinerar", "viaggio", "vacanza", "vacanze", "weekend", "giorni a ",
               "soggiorno", "tour", "cosa vedere", "cosa fare a", "visitare", "guida turistic",
               "voli", "hotel", "albergo"],
}

_CATEGORY_KW_PATTERNS = {
    cat: re.compile("|".join(re.escape(k) for k in kws), re.IGNORECASE)
    for cat, kws in CATEGORY_KEYWORDS.items()
}


def select_tool_names(user_message: str) -> set:
    """Return the names of tools to include for this user message."""
    selected = set(CORE_TOOLS)
    if not user_message:
        return selected
    for cat, pat in _CATEGORY_KW_PATTERNS.items():
        if pat.search(user_message):
            selected.update(CATEGORY_TOOLS.get(cat, set()))
    return selected


def filter_schemas(all_schemas, user_message: str):
    """Return only the schemas (in original order) that are relevant."""
    names = select_tool_names(user_message)
    return [s for s in all_schemas if s.get("name") in names]
