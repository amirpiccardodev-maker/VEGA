"""Analizza consumo API reale + simula token per chiamata tipo."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import memory
from personality import build_system_prompt
import tools as tool_registry
import tool_router


def approx_tokens(s: str) -> int:
    """Rough approximation: 1 token ≈ 4 chars (English) / 3.5 chars (Italian)."""
    return int(len(s) / 3.7)


def schemas_tokens(schemas):
    s = json.dumps(schemas, ensure_ascii=False)
    return approx_tokens(s)


def main():
    print("=" * 70)
    print(" ANALISI CONSUMO API VEGA")
    print("=" * 70)

    # 1. Usage reali
    u = memory.get_usage_summary()
    print("\n[1] USAGE REALE")
    print(f"  Oggi:    ${u['today_cost_usd']:.4f}  ({u['today'].get('calls', 0)} chiamate)")
    print(f"  Totale:  ${u['total_cost_usd']:.4f}  ({u['total'].get('calls', 0)} chiamate)")
    daily = memory.get_all().get("usage", {}).get("daily", {})
    print(f"\n  Ultimi {len(daily)} giorni:")
    for date in sorted(daily.keys())[-10:]:
        d = daily[date]
        c = memory.estimate_cost(d)
        print(f"    {date}: {d.get('calls',0):3d} call | "
              f"in={d.get('input',0):6d} out={d.get('output',0):5d} "
              f"cw={d.get('cache_write',0):6d} cr={d.get('cache_read',0):6d} "
              f"= ${c:.4f}")

    # 2. System prompt analysis
    sp = build_system_prompt()
    sp_tokens = approx_tokens(sp)
    print(f"\n[2] SYSTEM PROMPT")
    print(f"  Caratteri: {len(sp)}")
    print(f"  Token (stima): {sp_tokens}")
    print(f"  Cached: si (ephemeral)")

    # Breakdown system prompt
    facts = memory.get_facts()
    instr = memory.get_instructions()
    prefs = memory.get_preferences()
    print(f"  - Fatti utente: {len(facts)} ({approx_tokens(json.dumps(facts, ensure_ascii=False))} tok)")
    print(f"  - Istruzioni custom: {len(instr)} ({approx_tokens(json.dumps(instr, ensure_ascii=False))} tok)")
    print(f"  - Home location: {prefs.get('home_location', 'none')}")

    # 3. Tool schemas analysis
    all_schemas = tool_registry.all_schemas()
    all_tok = schemas_tokens(all_schemas)
    print(f"\n[3] TOOL SCHEMAS")
    print(f"  Totale tool: {len(all_schemas)}")
    print(f"  Token tutti i tool: {all_tok}")

    # Test routing per query tipiche
    test_queries = [
        ("che ore sono", "frase semplice"),
        ("dimmi le notizie e il meteo", "doppio tool"),
        ("leggi le mail e dimmi se ce qualcosa urgente", "email + analisi"),
        ("creami un itinerario di 3 giorni a roma", "complesso multi-tool"),
        ("fammi vedere foto di milano", "ricerca immagini"),
        ("ciao", "shortcut locale (no Claude)"),
    ]
    print(f"\n  Router filter per query tipiche:")
    print(f"  {'Query':<60} {'Tool':>5} {'Tok':>5}")
    for q, desc in test_queries:
        filtered = tool_router.filter_schemas(all_schemas, q)
        tok = schemas_tokens(filtered)
        print(f"  {(q + ' (' + desc + ')')[:60]:<60} {len(filtered):>5} {tok:>5}")

    # 4. Cost per call estimate
    print(f"\n[4] COSTO PER CHIAMATA TIPICA")
    print(f"  Tariffe Claude Sonnet 4.5: $3/M input, $15/M output,")
    print(f"  $3.75/M cache write (1.25x), $0.30/M cache read (0.1x)")
    print()
    print(f"  Scenario A: PRIMA chiamata dopo 5 min idle (cache MISS)")
    sys_in = sp_tokens
    tools_in = schemas_tokens(tool_router.filter_schemas(all_schemas, "che tempo fa"))
    user_in = 20
    history_in = 0  # primo turno
    output = 100
    write = sys_in + tools_in
    direct = user_in + history_in
    cost = (write * 3.75 + direct * 3 + output * 15) / 1_000_000
    print(f"    System+tools (cache write): {write} tok")
    print(f"    Messaggi (no cache): {direct} tok")
    print(f"    Output: {output} tok")
    print(f"    Costo: ${cost:.5f}")
    print()
    print(f"  Scenario B: chiamata seguente entro 5 min (cache HIT)")
    read = write  # stessi token, ma scontati
    cost = (read * 0.30 + direct * 3 + output * 15) / 1_000_000
    print(f"    System+tools (cache read): {read} tok")
    print(f"    Messaggi (no cache): {direct} tok")
    print(f"    Output: {output} tok")
    print(f"    Costo: ${cost:.5f} ← molto piu' basso")
    print()
    print(f"  Scenario C: chiamata con tool use (2 round-trip)")
    tool_result_in = 1500
    history_growth = tool_result_in + 200  # tool_result + assistant tool_use
    cost = (read * 0.30 + (direct + tool_result_in) * 3 + 200 * 15) / 1_000_000
    cost += (read * 0.30 + (direct + tool_result_in + history_growth) * 3 + output * 15) / 1_000_000
    print(f"    Costo (2 chiamate): ${cost:.5f}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
