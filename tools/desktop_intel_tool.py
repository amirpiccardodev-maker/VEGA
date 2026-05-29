"""Tool per controllare il desktop intelligence (opt-in)."""

TOOLS = [
    {"name": "desktop_intel_enable",
     "description": "Attiva osservazione passiva del desktop per pattern learning. Default OFF. Salva pattern d'uso, non invia mai dati a Claude senza consent.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "desktop_intel_disable",
     "description": "Disattiva osservazione desktop.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "desktop_intel_status",
     "description": "Stato attuale del desktop intelligence + pattern rilevati.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "desktop_intel_patterns",
     "description": "Mostra i pattern d'uso scoperti.",
     "input_schema": {"type": "object", "properties": {}}},
]


def run(name, args):
    import memory
    import desktop_observer as di

    if name == "desktop_intel_enable":
        di.start()
        memory.set_preference("desktop_intelligence", True)
        return ("Desktop intelligence ATTIVA. Osservera' la tua attivita' e dopo "
                "qualche giorno proporra' automazioni basate sui tuoi pattern. "
                "Tutti i dati restano locali.")

    if name == "desktop_intel_disable":
        di.stop()
        memory.set_preference("desktop_intelligence", False)
        return "Desktop intelligence disattivata."

    if name == "desktop_intel_status":
        st = di.get_status()
        return (f"Active: {st['active']}\n"
                f"Window watcher: {'attivo' if st['watcher_alive'] else 'spento'}\n"
                f"Pattern learner: {'attivo' if st['learner_alive'] else 'spento'}")

    if name == "desktop_intel_patterns":
        try:
            import memory_graph as mg
            patterns = mg.list_by_kind("behavioral", limit=20)
            if not patterns:
                return "Nessun pattern ancora rilevato. Servono qualche giorno di osservazione."
            return "\n".join(f"- {p['content']}" for p in patterns)
        except Exception as e:
            return f"Errore: {e}"

    return "?"
