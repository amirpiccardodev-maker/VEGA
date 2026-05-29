"""Event bus in-process per Vega.

Foundation per:
  - decoupling moduli (publish vs direct call)
  - audit trail eventi (events.log JSONL)
  - retry/dedup centralizzato
  - debug/replay

Thread-safe. Zero dipendenze esterne.

API:
    bus.publish(topic, payload, persist=False, priority="normal")
    bus.subscribe(topic, handler)   # handler(event_dict) -> None
    bus.replay(topic, limit=20)     # ultimi eventi di un topic
    bus.history()                    # ultimi 100 eventi globali
"""
import json
import os
import queue
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "events.log"   # JSONL persistent log
MEM_RING = 200                    # in-memory ring buffer size per topic
PRIORITIES = {"high": 0, "normal": 5, "low": 10}


class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)   # topic -> [handler, ...]
        self._lock = threading.RLock()
        self._mem = defaultdict(lambda: deque(maxlen=MEM_RING))  # topic -> ring
        self._global = deque(maxlen=500)
        self._async_q = queue.PriorityQueue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._async_loop, daemon=True)
        self._worker.start()

    def publish(self, topic: str, payload: dict = None,
                persist: bool = False, priority: str = "normal",
                sync: bool = True):
        """Pubblica un evento sul bus.

        sync=True: handler invocati nello stesso thread (default per UI)
        sync=False: in coda async (per handler lenti)
        """
        event = {
            "id": uuid.uuid4().hex[:12],
            "topic": topic,
            "ts": time.time(),
            "payload": payload or {},
        }
        with self._lock:
            self._mem[topic].append(event)
            self._global.append(event)
            handlers = list(self._subs.get(topic, []))
            wildcards = list(self._subs.get("*", []))

        if persist:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            except Exception:
                pass

        # Invoke handlers
        all_handlers = handlers + wildcards
        if sync:
            for h in all_handlers:
                try:
                    h(event)
                except Exception as e:
                    # Don't let one bad handler kill the publish
                    print(f"[bus] handler error on {topic}: {e}")
        else:
            prio = PRIORITIES.get(priority, 5)
            self._async_q.put((prio, time.time(), event, all_handlers))

        return event["id"]

    def subscribe(self, topic: str, handler):
        """Registra un handler. Topic '*' = catch-all."""
        with self._lock:
            self._subs[topic].append(handler)
        return lambda: self.unsubscribe(topic, handler)

    def unsubscribe(self, topic: str, handler):
        with self._lock:
            if handler in self._subs.get(topic, []):
                self._subs[topic].remove(handler)

    def replay(self, topic: str, limit: int = 20) -> list:
        with self._lock:
            return list(self._mem.get(topic, []))[-limit:]

    def history(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._global)[-limit:]

    def topics(self) -> list:
        with self._lock:
            return sorted([t for t, h in self._subs.items() if h])

    def stop(self):
        self._stop.set()

    def _async_loop(self):
        while not self._stop.is_set():
            try:
                prio, ts, event, handlers = self._async_q.get(timeout=0.5)
            except queue.Empty:
                continue
            for h in handlers:
                try:
                    h(event)
                except Exception as e:
                    print(f"[bus async] {event['topic']}: {e}")


# Singleton
_INSTANCE = None
_INSTANCE_LOCK = threading.Lock()


def _get():
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = EventBus()
    return _INSTANCE


def publish(topic, payload=None, persist=False, priority="normal", sync=True):
    return _get().publish(topic, payload, persist, priority, sync)


def subscribe(topic, handler):
    return _get().subscribe(topic, handler)


def unsubscribe(topic, handler):
    _get().unsubscribe(topic, handler)


def replay(topic, limit=20):
    return _get().replay(topic, limit)


def history(limit=50):
    return _get().history(limit)


def topics():
    return _get().topics()


def stop():
    _get().stop()


# Standard topic names (per evitare typo)
class Topics:
    USER_COMMAND = "user.command"        # testo/voce ricevuti
    STATE_CHANGED = "state.changed"       # engine state change
    TOOL_INVOKED = "tool.invoked"        # prima di execute
    TOOL_EXECUTED = "tool.executed"       # dopo, con result
    MEMORY_FACT = "memory.fact_added"
    MEMORY_NOTE = "memory.note_added"
    MEMORY_TODO = "memory.todo_added"
    AUTOMATION_FIRE = "automation.fire"
    CARD_SHOWN = "card.shown"
    CONVERSATION_EXCHANGE = "conversation.exchange"
    ERROR = "error.occurred"
    TASK_ENQUEUED = "task.enqueued"
    TASK_STARTED = "task.started"
    TASK_OK = "task.ok"
    TASK_FAILED = "task.failed"
    TASK_RETRIED = "task.retried"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP = "workflow.step"
    WORKFLOW_COMPLETED = "workflow.completed"
    AGENT_PLAN = "agent.plan"
    AGENT_EXECUTE = "agent.execute"
    AGENT_REFLECT = "agent.reflect"
    DESKTOP_WINDOW = "desktop.window_changed"
    DESKTOP_PATTERN = "desktop.pattern_detected"
