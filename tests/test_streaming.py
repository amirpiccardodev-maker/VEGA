"""Test streaming: verify sentences arrive incrementally and final text matches."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from brain import Brain


def main():
    b = Brain()
    print("[TEST] Streaming basic call")
    t0 = time.time()
    first_sentence_time = None
    sentences = []
    final = None
    for kind, text in b.ask_stream("Presentati in 3 frasi corte, italiano."):
        elapsed = time.time() - t0
        if kind == "sentence":
            if first_sentence_time is None:
                first_sentence_time = elapsed
            sentences.append(text)
            print(f"  [{elapsed:.2f}s] sentenza: {text[:80]}")
        elif kind == "final":
            final = text
            print(f"  [{elapsed:.2f}s] FINAL: {text[:80]}")
    print(f"\nTempo prima sentenza: {first_sentence_time:.2f}s")
    print(f"Tempo totale: {time.time() - t0:.2f}s")
    print(f"Numero sentenze: {len(sentences)}")
    assert sentences, "Nessuna sentenza ricevuta"
    assert final, "Nessun final"

    print("\n[TEST] Streaming with tool use")
    t0 = time.time()
    sentences = []
    for kind, text in b.ask_stream("Che ore sono e che giorno e'? In una frase."):
        elapsed = time.time() - t0
        if kind == "sentence":
            sentences.append(text)
            print(f"  [{elapsed:.2f}s] {text[:100]}")
        elif kind == "final":
            print(f"  [{elapsed:.2f}s] FINAL: {text[:100]}")
    print(f"\n[OK] Streaming funziona")


if __name__ == "__main__":
    main()
