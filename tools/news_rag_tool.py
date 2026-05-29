"""Tool: cerca tra le news ingerite continuamente in memoria."""

TOOLS = [{
    "name": "ask_recent_news",
    "description": (
        "[OFFLINE/CACHE] Cerca tra le notizie già raccolte e indicizzate "
        "localmente da feed RSS (memoria locale, no network). "
        "VELOCE (~100ms), no costi. Risultati limitati a quanto raccolto "
        "negli ultimi giorni. USA SE: query su un argomento generale "
        "non urgente E hai bisogno di velocità. "
        "DIFFERENZA da get_news: get_news fa fetch LIVE da web (più fresco "
        "ma più lento ~2s)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Argomento da cercare."},
            "limit": {"type": "integer", "description": "Max risultati (default 5)."},
        },
        "required": ["query"],
    },
}]


def run(name, args):
    import news_graph
    q = (args or {}).get("query", "").strip()
    if not q:
        return "Specifica una query."
    limit = int((args or {}).get("limit", 5))
    results = news_graph.search_recent(q, top_k=limit)
    if not results:
        return "Nessuna notizia recente trovata su questo argomento."
    out_lines = []
    for r in results:
        content = r.get("content", "").strip()
        sim = r.get("similarity", 0)
        out_lines.append(f"- {content[:300]} (rel: {sim:.2f})")
    return "Notizie recenti rilevanti:\n" + "\n".join(out_lines)
