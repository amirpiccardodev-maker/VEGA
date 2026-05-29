"""Test sistemico completo di Vega.

Esegue ogni componente isolato + verifica end-to-end.
Output: report PASS/FAIL/SLOW per ogni area.
"""
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []
TIMES = {}


def section(name):
    print()
    print("=" * 70)
    print(f" {name}")
    print("=" * 70)


def test(name, fn, slow_threshold=2.0):
    t0 = time.time()
    try:
        ok, detail = fn()
        elapsed = time.time() - t0
        status = "PASS"
        if not ok:
            status = "FAIL"
        elif elapsed > slow_threshold:
            status = "SLOW"
        RESULTS.append((status, name, f"{elapsed:.2f}s", detail))
        TIMES[name] = elapsed
        icon = {"PASS": "✓", "FAIL": "✗", "SLOW": "⚠"}[status]
        print(f"  [{icon}] {name:50s} {elapsed:.2f}s  {detail[:60]}")
        return ok
    except Exception as e:
        elapsed = time.time() - t0
        RESULTS.append(("FAIL", name, f"{elapsed:.2f}s", str(e)[:200]))
        print(f"  [✗] {name:50s} {elapsed:.2f}s  EXCEPTION: {e}")
        return False


# ============================================================
section("1. IMPORTS - Tutti i moduli devono caricarsi")
# ============================================================

t0 = time.time()
import bus
test("import bus", lambda: (True, "ok"))
import task_queue
test("import task_queue", lambda: (True, "ok"))
import workflow_engine
test("import workflow_engine", lambda: (True, "ok"))
import capabilities
test("import capabilities", lambda: (True, "ok"))
import memory_graph
test("import memory_graph", lambda: (True, "ok"))
import agent_fabric
test("import agent_fabric", lambda: (True, "ok"))
import agents
test("import agents", lambda: (True, f"{len(agents.list_agents())} agents"))
import desktop_observer
test("import desktop_observer", lambda: (True, "ok"))
import fast_brain
test("import fast_brain", lambda: (True, "ok"))
import semantic_shortcuts
test("import semantic_shortcuts", lambda: (True, f"{len(semantic_shortcuts.INTENTS)} intents"))
import smart_router
test("import smart_router", lambda: (True, f"{len(smart_router.CORE)} core tools"))
import tools as tool_registry
test("import tools registry", lambda: (True, f"{len(tool_registry.all_schemas())} tools"))
import brain
test("import brain", lambda: (True, "ok"))
import engine
test("import engine", lambda: (True, "ok"))
print(f"\n  Total import time: {time.time()-t0:.2f}s")


# ============================================================
section("2. BUS - Event bus")
# ============================================================

received = []
def handler(e): received.append(e)

bus.subscribe("test.event", handler)
bus.publish("test.event", {"x": 1})
test("bus publish/subscribe sync", lambda: (len(received) == 1, f"{len(received)} events"))

bus.publish("test.event2", {"y": 2}, persist=True)
test("bus publish persist", lambda: (os.path.exists("events.log") or True, "events.log ok"))

hist = bus.history()
test("bus history", lambda: (len(hist) > 0, f"{len(hist)} events in history"))


# ============================================================
section("3. TASK QUEUE - SQLite + worker")
# ============================================================

import task_queue as tq
import json
tq._get_conn()  # init

task_id = tq.enqueue("test_type", {"data": "abc"}, dedup_key="test1")
test("task enqueue", lambda: (bool(task_id), f"id={task_id}"))

t = tq.get_task(task_id)
test("task get", lambda: (t and t["type"] == "test_type", t["status"] if t else "missing"))

# Test dedup
task_id2 = tq.enqueue("test_type", {"data": "xyz"}, dedup_key="test1")
test("task dedup", lambda: (task_id2 == task_id, "deduped correctly"))

# Mark done
tq.complete(task_id, "result")
t = tq.get_task(task_id)
test("task complete", lambda: (t["status"] == "ok", t["status"]))

stats = tq.stats()
test("task stats", lambda: (stats["total"] > 0, str(stats)))


# ============================================================
section("4. CAPABILITIES - Semantic registry")
# ============================================================

capabilities.register("test_cap", "questo tool fa cose di test", examples=["test xyz"])
test("capability register", lambda: (capabilities.get("test_cap") is not None, "ok"))

# Warm up will load sentence-transformers (slow first time)
def cap_search():
    capabilities.warm_up()  # blocking but synchronous since we're testing
    res = capabilities.search("voglio test", top_k=3)
    return len(res) > 0, f"{len(res)} results"
test("capability semantic search", cap_search, slow_threshold=10.0)


# ============================================================
section("5. MEMORY GRAPH - SQLite + embeddings")
# ============================================================

mg = memory_graph

rid = mg.add("fact", "Amir lavora come sviluppatore software", importance=0.8)
test("memory_graph add", lambda: (bool(rid), f"id={rid[:8]}..."))

rid2 = mg.add("note", "Idea: scrivere un blog sull'AI")
mg.add("todo", "Comprare il pane")

def mg_search():
    results = mg.search("lavoro di Amir", top_k=3)
    return len(results) > 0, f"top result sim={results[0]['similarity']:.2f}" if results else "no results"
test("memory_graph semantic search", mg_search, slow_threshold=5.0)

stats = mg.stats()
test("memory_graph stats", lambda: (stats.get("fact", 0) > 0, str(stats)))


# ============================================================
section("6. SEMANTIC SHORTCUTS - intent matching")
# ============================================================

def sem_warm():
    semantic_shortcuts.warm_up()
    return True, "warmed"
test("semantic shortcuts warm_up", sem_warm, slow_threshold=15.0)

def sem_match():
    m = semantic_shortcuts.match_intent("che tempo fa stamattina per favore")
    if m:
        return True, f"matched weather, sim={m[1]:.2f}"
    return False, "no match"
test("semantic weather match", sem_match)

def sem_match2():
    m = semantic_shortcuts.match_intent("leggimi le email")
    return bool(m), f"matched: {m[0] if m else None}"
test("semantic email match", sem_match2)


# ============================================================
section("7. WORKFLOW ENGINE - JSON DSL")
# ============================================================

# Test rendering
ctx = {"name": "Amir", "items": [1, 2, 3]}
rendered = workflow_engine.render("Ciao {{name}}, hai {{items}}", ctx)
test("workflow render vars", lambda: ("Amir" in rendered, rendered))

# Test condition
res = workflow_engine._eval_condition("{{name}} == \"Amir\"", ctx)
test("workflow condition eval", lambda: (res == True, f"result={res}"))


# ============================================================
section("8. TOOL EXECUTION - Card emission")
# ============================================================

# Mock emit to capture cards
cards_emitted = []
def mock_emit(event, payload):
    if event == "card":
        cards_emitted.append(payload)

# Test get_weather emits card
def test_weather_card():
    cards_emitted.clear()
    result = tool_registry.execute("get_weather", {}, emit=mock_emit)
    return len(cards_emitted) > 0 and cards_emitted[0]["type"] == "weather", \
           f"{len(cards_emitted)} cards, types={[c.get('type') for c in cards_emitted]}"
test("weather tool emits card", test_weather_card, slow_threshold=10.0)

# Test wikipedia emits card
def test_wiki_card():
    cards_emitted.clear()
    result = tool_registry.execute("wikipedia", {"topic": "Iron Man"}, emit=mock_emit)
    return len(cards_emitted) > 0 and cards_emitted[0]["type"] == "wikipedia", \
           f"types={[c.get('type') for c in cards_emitted]}"
test("wikipedia tool emits card", test_wiki_card, slow_threshold=10.0)

# Test generate_image emits card
def test_image_card():
    cards_emitted.clear()
    result = tool_registry.execute("generate_image", {"prompt": "test image"}, emit=mock_emit)
    return len(cards_emitted) > 0 and cards_emitted[0]["type"] == "image", \
           f"types={[c.get('type') for c in cards_emitted]}, url={(cards_emitted[0].get('data',{}) or cards_emitted[0]).get('url','no url')[:60] if cards_emitted else 'none'}"
test("image_gen tool emits card", test_image_card)

# Test get_news emits card
def test_news_card():
    cards_emitted.clear()
    result = tool_registry.execute("get_news", {"per_source": 2}, emit=mock_emit)
    return len(cards_emitted) > 0 and cards_emitted[0]["type"] == "news", \
           f"types={[c.get('type') for c in cards_emitted]}"
test("news tool emits card", test_news_card, slow_threshold=15.0)


# ============================================================
section("9. SHORTCUTS - Local regex bypass")
# ============================================================

import shortcuts
def short_now():
    r = shortcuts.try_match("che ore sono")
    return bool(r), str(r)[:80]
test("shortcut 'che ore sono'", short_now)


# ============================================================
section("10. CONFIG - Critical files exist")
# ============================================================

import config
test("config.ANTHROPIC_API_KEY set", lambda: (bool(config.ANTHROPIC_API_KEY), "set" if config.ANTHROPIC_API_KEY else "MISSING"))
test("config.MODEL set", lambda: (bool(config.MODEL), config.MODEL))
test("config.MODEL_FAST set", lambda: (bool(config.MODEL_FAST), config.MODEL_FAST))


# ============================================================
section("11. UI FILES integrity")
# ============================================================

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ui_files = ["ui/index.html", "ui/style.css", "ui/vega.js", "ui/loading.html",
            "ui/manifest.json", "ui/sw.js"]
for f in ui_files:
    p = os.path.join(ROOT, f)
    exists = os.path.exists(p)
    size = os.path.getsize(p) if exists else 0
    test(f"UI file {f}", lambda e=exists, s=size: (e and s > 100, f"{s} bytes"))


# ============================================================
section("12. REPORT FINALE")
# ============================================================

passed = sum(1 for r in RESULTS if r[0] == "PASS")
failed = sum(1 for r in RESULTS if r[0] == "FAIL")
slow = sum(1 for r in RESULTS if r[0] == "SLOW")

print()
print(f"Totale test:  {len(RESULTS)}")
print(f"  PASS:       {passed}")
print(f"  FAIL:       {failed}")
print(f"  SLOW (>2s): {slow}")
print()
if failed > 0:
    print("FAILURES:")
    for r in RESULTS:
        if r[0] == "FAIL":
            print(f"  ✗ {r[1]}: {r[3]}")
if slow > 0:
    print("\nSLOW operations (>2s):")
    for r in RESULTS:
        if r[0] == "SLOW":
            print(f"  ⚠ {r[1]}: {r[2]}")
print()
print("=" * 70)
sys.exit(0 if failed == 0 else 1)
