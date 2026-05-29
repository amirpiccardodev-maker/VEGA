"""Verify that prompt caching is actually working."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from brain import Brain
import memory


def main():
    print("=" * 50)
    print(" TEST PROMPT CACHING")
    print("=" * 50)

    # Baseline
    before = memory.get_usage_summary()
    print(f"Usage prima: today={before['today_cost_usd']:.6f}$")

    b = Brain()

    # 1st call: this writes the cache
    print("\n[1] Prima chiamata (cache write attesa)...")
    r1 = b.ask("Ciao Vega.")
    print(f"   Reply: {r1[:80]}")

    after1 = memory.get_usage_summary()
    delta1 = {
        k: after1["today"].get(k, 0) - before["today"].get(k, 0)
        for k in ("input", "output", "cache_write", "cache_read")
    }
    print(f"   Token: input={delta1['input']} output={delta1['output']} "
          f"cache_write={delta1['cache_write']} cache_read={delta1['cache_read']}")

    # 2nd call: this should hit the cache
    print("\n[2] Seconda chiamata immediata (cache read attesa)...")
    r2 = b.ask("Come stai?")
    print(f"   Reply: {r2[:80]}")

    after2 = memory.get_usage_summary()
    delta2 = {
        k: after2["today"].get(k, 0) - after1["today"].get(k, 0)
        for k in ("input", "output", "cache_write", "cache_read")
    }
    print(f"   Token: input={delta2['input']} output={delta2['output']} "
          f"cache_write={delta2['cache_write']} cache_read={delta2['cache_read']}")

    if delta2["cache_read"] > 0:
        print(f"\n[OK] CACHE FUNZIONA: {delta2['cache_read']} token serviti dalla cache")
        savings = delta2["cache_read"] * 0.9 * 3.0 / 1_000_000
        print(f"     Risparmio stimato sulla 2a chiamata: ${savings:.6f}")
    else:
        print("\n[WARN] Nessun cache hit rilevato. Possibile cache miss "
              "(system prompt diverso, o cache scaduta).")

    print(f"\nCosto totale del test: ${after2['today_cost_usd'] - before['today_cost_usd']:.6f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
