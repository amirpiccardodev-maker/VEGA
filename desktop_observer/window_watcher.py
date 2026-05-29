"""Window watcher: rileva l'app/finestra attiva ogni 5s.

Pubblica sul bus quando cambia. Salva in memory_graph come kind=episodic.
"""
import threading
import time

import bus


class WindowWatcher(threading.Thread):
    INTERVAL = 5  # seconds

    def __init__(self):
        super().__init__(daemon=True, name="WindowWatcher")
        self._stop = threading.Event()
        self._last_title = None
        self._last_app = None

    def stop(self):
        self._stop.set()

    def _get_active_window(self):
        """Returns (title, app_name) of current foreground window."""
        try:
            import pygetwindow as gw
            w = gw.getActiveWindow()
            if not w:
                return None, None
            title = w.title or ""
            # Heuristic for app: first " - " separator
            app = title.split(" - ")[-1] if " - " in title else title.split(" — ")[-1]
            return title[:200], app[:80]
        except Exception:
            return None, None

    def run(self):
        while not self._stop.is_set():
            try:
                title, app = self._get_active_window()
                if title and (title != self._last_title or app != self._last_app):
                    self._last_title = title
                    self._last_app = app
                    bus.publish("desktop.window_changed", {
                        "title": title, "app": app, "ts": int(time.time())
                    })
                    # Save in memory_graph as episodic event (low importance, will be pruned)
                    try:
                        import memory_graph as mg
                        mg.add("episodic", f"finestra attiva: {app or title}",
                               importance=0.1, source="window_watcher",
                               ttl_sec=7*86400)  # auto-expire 7 days
                    except Exception:
                        pass
            except Exception as e:
                bus.publish("error.occurred", {"source": "window_watcher", "error": str(e)})
            self._stop.wait(self.INTERVAL)
