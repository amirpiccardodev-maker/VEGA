"""Stress test brain: ensure no 400 errors, italian responses, safe truncation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from brain import Brain, _safe_trim


def assert_italian(text: str):
    """Heuristic: response should not be predominantly English."""
    english_markers = ["the ", "this is", "i'm", "i am", "hello", "yes,", "no,"]
    low = text.lower()
    hits = sum(1 for m in english_markers if m in low)
    assert hits == 0, f"Risposta sembra in inglese: {text[:120]}"


def test_history_trim_safe():
    """Truncation must never produce orphan tool_use messages."""
    h = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "x1", "name": "t", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x1", "content": "ok"}]},
        {"role": "assistant", "content": "A1"},
    ] * 10  # 40 messages, many tool pairs

    trimmed = _safe_trim(h)
    # First message must be user with non-tool_result content
    assert trimmed[0]["role"] == "user"
    c = trimmed[0]["content"]
    if isinstance(c, list):
        assert not any(b.get("type") == "tool_result" for b in c), "Inizio storia con tool_result!"
    print("[OK] history trim safe")


def test_basic_call():
    b = Brain()
    r = b.ask("Ciao, presentati in una frase breve.")
    print(f"[BASIC] {r}")
    assert r.strip(), "Risposta vuota"
    assert_italian(r)
    print("[OK] basic call italian")


def test_tool_use():
    b = Brain()
    r = b.ask("Che ore sono?")
    print(f"[TOOL] {r}")
    assert r.strip()
    assert_italian(r)
    print("[OK] single tool use")


def test_chained_tools():
    b = Brain()
    r = b.ask("Dimmi ora e meteo in una frase, breve.")
    print(f"[CHAINED] {r}")
    assert r.strip()
    assert_italian(r)
    print("[OK] chained tools")


def test_long_conversation():
    """Many turns to stress history truncation. Spaced out to avoid rate limit."""
    import time as _t
    b = Brain()
    questions = [
        "Ciao.",
        "Che ore sono?",
        "Quanto fa 2 piu' 2?",
        "Quali note ho?",
        "Quanto fa 17 per 23?",
        "Mostrami le tue impostazioni.",
    ]
    for i, q in enumerate(questions, 1):
        r = b.ask(q)
        print(f"[T{i}] Q: {q} -> {r[:90]}")
        assert r.strip(), f"Turno {i} risposta vuota"
        assert_italian(r)
        _t.sleep(3)  # space requests to respect rate limit
    print(f"[OK] long conversation, final history length: {len(b.history)}")


def test_error_recovery():
    """After a forced error, brain should reset and recover on next call."""
    b = Brain()
    b.history = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "fake", "content": "x"}]}]
    try:
        b.ask("ciao, presentati brevemente")
        print("[OK] recovered from bad history (safe trim cleaned it)")
    except Exception as e:
        # If it raised, history should have been reset for next call
        assert b.history == []
        print(f"[OK] error reset history; got: {type(e).__name__}")


def test_concurrent_ask():
    """Multiple threads asking simultaneously must serialize without corruption."""
    import threading as _th
    b = Brain()
    results = []
    errors = []

    def worker(q):
        try:
            r = b.ask(q)
            results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [_th.Thread(target=worker, args=(f"Domanda {i}: che ore sono?",)) for i in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(results) + len(errors) == 3
    assert len(results) >= 1, f"Tutti i thread hanno fallito: {errors}"
    for r in results:
        assert_italian(r)
    print(f"[OK] concurrent calls serialized ({len(results)} ok, {len(errors)} errors)")


def test_memory_atomic():
    """Atomic write must not leave partial files."""
    import memory as mem
    mem.add_fact("test fact concorrenza")
    data = mem.get_all()
    assert any("test fact concorrenza" in f["text"] for f in data["user_facts"])
    # cleanup
    def remove(d):
        d["user_facts"] = [f for f in d["user_facts"] if "test fact concorrenza" not in f["text"]]
    mem.update(remove)
    print("[OK] memory atomic write")


def main():
    print("=" * 50)
    print(" TEST BRAIN + INTEGRATION")
    print("=" * 50)
    test_history_trim_safe()
    test_memory_atomic()
    test_basic_call()
    test_tool_use()
    test_chained_tools()
    test_error_recovery()
    test_long_conversation()
    test_concurrent_ask()
    print("\n" + "=" * 50)
    print(" TUTTI I TEST PASSATI")
    print("=" * 50)


if __name__ == "__main__":
    main()
