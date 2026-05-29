"""Shortcut semantici via embeddings (sentence-transformers).

Mantiene una lista di 'intent templates' con frasi tipo e azione associata.
Per ogni query utente:
  1. Calcola embedding
  2. Trova il template piu' simile (cosine similarity)
  3. Se sim > THRESHOLD, esegue l'azione bypassando Claude

Modello: paraphrase-multilingual-MiniLM-L12-v2 (gia' usato per RAG, condiviso).
Costo per query: 1 embedding ~10ms su CPU.
"""
import threading
import numpy as np


# Threshold di similarita' per fire l'intent. Calibrato empiricamente:
#   > 0.85 = molto sicuro (poche false positive)
#   0.75-0.85 = sicuro
#   < 0.75 = troppi falsi positivi
THRESHOLD = 0.78


# Intent templates: (lista di frasi tipo, action_dict)
# action_dict = {"tool": "<name>", "args": {...}}  oppure
#               {"template": "<reply string>"}      oppure
#               {"command": "<text to pass to engine>"}
INTENTS = [
    # ====== VISION ======
    {
        "phrases": [
            "guarda lo schermo", "guarda il mio schermo", "cosa c'e sullo schermo",
            "cosa vedi sullo schermo", "descrivi lo schermo", "analizza lo schermo",
            "fai uno screenshot e dimmi", "vedi cosa sto facendo", "che cosa c'e a video",
        ],
        "action": {"tool": "analyze_screen", "args": {"region": "full"}},
    },

    # ====== TIME / DATA ======
    {
        "phrases": ["che ore sono", "che ora e", "dimmi l'ora", "che orario e", "ora attuale", "ora esatta"],
        "action": {"local": "now"},
    },
    {
        "phrases": ["che giorno e", "che giorno e oggi", "che data e", "data di oggi", "che data e oggi"],
        "action": {"local": "date"},
    },

    # ====== METEO ======
    {
        "phrases": [
            "che tempo fa", "che tempo c'e", "com'e il tempo", "che meteo fa", "meteo oggi",
            "che tempo fara oggi", "dimmi il meteo", "che tempo fa fuori", "che tempo fa stamattina",
            "che tempo fa nel pomeriggio", "che tempo c'e adesso", "che temperatura c'e",
        ],
        "action": {"tool": "get_weather", "args": {}},
    },
    {
        "phrases": ["meteo domani", "che tempo fa domani", "previsioni domani", "domani che tempo fa"],
        "action": {"tool": "get_weather", "args": {"days": 1}},
    },
    {
        "phrases": ["meteo dopodomani", "previsioni 3 giorni", "previsioni settimana"],
        "action": {"tool": "get_weather", "args": {"days": 3}},
    },

    # ====== NEWS ======
    {
        "phrases": [
            "dimmi le notizie", "dammi le notizie", "leggi le notizie", "che notizie ci sono",
            "rassegna stampa", "ultime notizie", "notizie di oggi", "notizie del giorno",
            "cosa succede nel mondo", "cosa c'e di nuovo nelle news", "ultime news",
        ],
        "action": {"tool": "get_news", "args": {}},
    },
    {
        "phrases": [
            "notizie sport", "notizie sportive", "come va lo sport", "cosa succede nello sport",
            "ultime sportive", "sport di oggi", "sport oggi",
        ],
        "action": {"tool": "sports_news", "args": {}},
    },

    # ====== EMAIL ======
    {
        "phrases": [
            "leggi le email", "leggi le mie email", "leggi le mie mail", "ho mail nuove",
            "controlla la mail", "controlla la posta", "leggi la posta", "vedi le mie email",
            "che mail ho", "che email ho ricevuto", "elenca le mail recenti",
        ],
        "action": {"tool": "list_emails", "args": {"limit": 10}},
    },
    {
        "phrases": [
            "riassumi le email", "riassumi la posta", "riassumi inbox", "dammi un riassunto delle mail",
            "fammi un riassunto delle email",
        ],
        "action": {"tool": "summarize_inbox", "args": {"limit": 15}},
    },

    # ====== SISTEMA PC ======
    {
        "phrases": [
            "come va il sistema", "come sta il pc", "stato pc", "stato sistema",
            "info sistema", "info pc", "performance pc", "quanto cpu sto usando",
        ],
        "action": {"tool": "system_info", "args": {}},
    },
    {
        "phrases": ["blocca il pc", "blocca pc", "metti il pc in blocco", "chiudi il pc col lock"],
        "action": {"tool": "lock_pc", "args": {}},
    },
    {
        "phrases": ["mostra desktop", "vai al desktop", "minimizza tutto", "nascondi le finestre"],
        "action": {"tool": "minimize_all", "args": {}},
    },
    {
        "phrases": ["fai screenshot", "fammi uno screenshot", "cattura schermata", "scatta schermo"],
        "action": {"tool": "take_screenshot", "args": {}},
    },
    {
        "phrases": [
            "alza il volume", "aumenta il volume", "alza il suono",
            "metti il volume al massimo", "volume al massimo",
        ],
        "action": {"tool": "set_volume", "args": {"percent": 80}},
    },
    {
        "phrases": [
            "abbassa il volume", "diminuisci il volume", "abbassa il suono",
            "metti il volume basso",
        ],
        "action": {"tool": "set_volume", "args": {"percent": 30}},
    },
    {
        "phrases": ["muta", "muta audio", "togli l'audio", "silenzia"],
        "action": {"tool": "mute_audio", "args": {"mute": True}},
    },
    {
        "phrases": ["smuta", "riattiva audio", "rimetti l'audio"],
        "action": {"tool": "mute_audio", "args": {"mute": False}},
    },

    # ====== MEMORIA ======
    {
        "phrases": [
            "cosa sai di me", "cosa ti ricordi di me", "elenca cosa sai di me",
            "che fatti hai memorizzato", "fammi vedere i fatti",
        ],
        "action": {"tool": "list_facts", "args": {}},
    },
    {
        "phrases": [
            "lista todo", "cose da fare", "che cose devo fare", "che cose ho da fare",
            "fammi vedere i todo", "lista delle cose da fare",
        ],
        "action": {"tool": "list_todos", "args": {}},
    },
    {
        "phrases": ["lista note", "fammi vedere le note", "che note ho", "elenca le note"],
        "action": {"tool": "list_notes", "args": {}},
    },

    # ====== SETTINGS / SECURITY ======
    {
        "phrases": [
            "mostra impostazioni", "fammi vedere le impostazioni", "che impostazioni hai",
            "stato configurazione",
        ],
        "action": {"tool": "show_settings", "args": {}},
    },
    {
        "phrases": [
            "stato sicurezza", "stato privacy", "come va la sicurezza",
            "controllo sicurezza", "stato cybersecurity",
        ],
        "action": {"tool": "security_status", "args": {}},
    },

    # ====== POLITENESS / SMALLTALK ======
    {
        "phrases": ["ciao", "ciao vega", "salve", "ehi", "ehi vega", "ehilà"],
        "action": {"template": "Ciao Amir. Eccomi."},
    },
    {
        "phrases": ["grazie", "ti ringrazio", "grazie mille", "grazie vega"],
        "action": {"template": "Figurati, sempre un piacere."},
    },
    {
        "phrases": [
            "come stai", "tutto bene", "come va", "che fai", "stai bene",
        ],
        "action": {"template": "Sistemi al massimo, grazie. Tu come stai?"},
    },
    {
        "phrases": ["buongiorno", "buongiorno vega", "buon giorno"],
        "action": {"local": "morning_greeting"},
    },
    {
        "phrases": ["buonasera", "buona sera", "buonasera vega"],
        "action": {"local": "evening_greeting"},
    },
    {
        "phrases": ["buonanotte", "buona notte", "vado a dormire"],
        "action": {"template": "Buonanotte, Amir. Riposati bene."},
    },
    {
        "phrases": ["ok", "va bene", "perfetto", "d'accordo", "ricevuto"],
        "action": {"template": "Ricevuto."},
    },

    # ====== TIMER ======
    # (i timer specifici con minuti vengono ancora gestiti da regex perche' parametrici)
    {
        "phrases": ["lista timer", "fammi vedere i timer", "che timer ho", "elenca i timer"],
        "action": {"tool": "timer_list", "args": {}},
    },
    {
        "phrases": ["ferma tutti i timer", "stoppa tutti i timer"],
        "action": {"tool": "timer_stop_all", "args": {}},
    },

    # ====== AUTOMAZIONI ======
    {
        "phrases": [
            "lista automazioni", "fammi vedere le automazioni", "che automazioni ho",
            "elenca le automazioni",
        ],
        "action": {"tool": "list_automations", "args": {}},
    },

    # ====== RADIO / MUSICA ======
    {
        "phrases": ["ferma la musica", "stoppa la musica", "spegni la musica", "togli la musica"],
        "action": {"music_stop": True},
    },

    # ====== SCENE ======
    {
        "phrases": [
            "modalita lavoro", "modalita di lavoro", "modo lavoro", "attiva lavoro",
            "passa al lavoro",
        ],
        "action": {"tool": "activate_scene", "args": {"name": "lavoro"}},
    },
    {
        "phrases": [
            "modalita relax", "modalita rilassamento", "passa al relax", "attiva relax",
        ],
        "action": {"tool": "activate_scene", "args": {"name": "relax"}},
    },
    {
        "phrases": [
            "modalita notte", "passa alla notte", "attiva modalita notte",
            "buonanotte modalita",
        ],
        "action": {"tool": "activate_scene", "args": {"name": "notte"}},
    },
    {
        "phrases": [
            "modalita studio", "passa allo studio", "attiva studio",
        ],
        "action": {"tool": "activate_scene", "args": {"name": "studio"}},
    },
]


_lock = threading.Lock()
_model = None
_template_embs = None  # numpy array (N, dim)
_index = None  # list of (intent_idx, phrase_idx) parallel to _template_embs


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model


def _build_index():
    global _template_embs, _index
    if _template_embs is not None:
        return
    with _lock:
        if _template_embs is not None:
            return
        model = _get_model()
        all_phrases = []
        idx = []
        for i, intent in enumerate(INTENTS):
            for j, p in enumerate(intent["phrases"]):
                all_phrases.append(p)
                idx.append((i, j))
        embs = model.encode(all_phrases, batch_size=32, show_progress_bar=False,
                            normalize_embeddings=True)
        _template_embs = np.asarray(embs, dtype=np.float32)
        _index = idx


def match_intent(text: str, threshold: float = THRESHOLD):
    """Returns (intent_dict, similarity) if best match >= threshold, else None."""
    if not text or len(text.strip()) < 2:
        return None
    _build_index()
    if _template_embs is None or len(_template_embs) == 0:
        return None
    try:
        model = _get_model()
        q = model.encode([text.lower().strip()], normalize_embeddings=True)
        q = np.asarray(q, dtype=np.float32)[0]
        sims = _template_embs @ q
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim >= threshold:
            intent_idx, _ = _index[best_idx]
            return (INTENTS[intent_idx]["action"], best_sim)
    except Exception:
        pass
    return None


def warm_up():
    """Pre-build the index at startup so first query is instant."""
    _build_index()
