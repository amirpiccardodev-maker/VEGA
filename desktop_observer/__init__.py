"""Desktop intelligence: osservazione passiva del desktop per pattern learning.

Default OFF. Attivato via preference 'desktop_intelligence' = True.
Tutto rimane LOCALE - mai inviato a Claude senza consent esplicito.

Componenti:
  - window_watcher: traccia active window/app
  - pattern_learner: scopre routine ricorrenti
  - suggestion_engine: propone automazioni

Eventi pubblicati sul bus:
  - desktop.window_changed
  - desktop.app_used
  - desktop.pattern_detected
"""
import threading

from .window_watcher import WindowWatcher
from .pattern_learner import PatternLearner

_active = False
_watcher = None
_learner = None


def is_active() -> bool:
    return _active


def start(emit=None):
    global _active, _watcher, _learner
    if _active:
        return
    _active = True
    _watcher = WindowWatcher()
    _learner = PatternLearner()
    _watcher.start()
    _learner.start()


def stop():
    global _active, _watcher, _learner
    _active = False
    if _watcher:
        _watcher.stop()
    if _learner:
        _learner.stop()
    _watcher = None
    _learner = None


def get_status() -> dict:
    return {
        "active": _active,
        "watcher_alive": bool(_watcher and _watcher.is_alive()),
        "learner_alive": bool(_learner and _learner.is_alive()),
    }
