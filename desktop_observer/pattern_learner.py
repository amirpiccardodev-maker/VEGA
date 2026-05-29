"""Pattern learner: scopre routine ricorrenti dalle attivita' desktop.

Approccio semplice (no ML):
- Aggrega per (giorno_settimana, ora) -> app frequenti
- Se app X compare > N volte alle Y:00 di lun-ven -> pattern!
- Pubblica desktop.pattern_detected
- Suggerisce automazioni via memoria
"""
import threading
import time
from collections import defaultdict
from datetime import datetime

import bus


class PatternLearner(threading.Thread):
    ANALYSIS_INTERVAL = 600  # 10 minuti
    MIN_OCCURRENCES = 3       # quante volte serve vedere un pattern per considerarlo

    def __init__(self):
        super().__init__(daemon=True, name="PatternLearner")
        self._stop = threading.Event()
        # {(weekday, hour_bucket, app): count}
        self._observations = defaultdict(int)
        self._detected_patterns = set()
        # subscribe to window events
        bus.subscribe("desktop.window_changed", self._on_window)

    def _on_window(self, event):
        try:
            app = event["payload"].get("app", "")
            if not app:
                return
            now = datetime.now()
            key = (now.weekday(), now.hour, app)
            self._observations[key] += 1
        except Exception:
            pass

    def _analyze(self):
        now = datetime.now()
        cur_wd = now.weekday()
        cur_hour = now.hour
        for (wd, hour, app), count in list(self._observations.items()):
            if count < self.MIN_OCCURRENCES:
                continue
            key = (wd, hour, app)
            if key in self._detected_patterns:
                continue
            # Mark as detected
            self._detected_patterns.add(key)
            day_name = ["lunedi","martedi","mercoledi","giovedi","venerdi","sabato","domenica"][wd]
            bus.publish("desktop.pattern_detected", {
                "weekday": day_name, "hour": hour, "app": app, "count": count
            })
            # Save in memory_graph
            try:
                import memory_graph as mg
                mg.add("behavioral",
                       f"Pattern: alle {hour}:00 di {day_name} usi spesso {app} ({count} volte)",
                       importance=0.6, source="pattern_learner")
            except Exception:
                pass

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._analyze()
            except Exception as e:
                bus.publish("error.occurred", {"source": "pattern_learner", "error": str(e)})
            self._stop.wait(self.ANALYSIS_INTERVAL)
