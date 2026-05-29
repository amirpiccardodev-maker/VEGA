"""Shared mutable state for tools to emit side events (e.g. UI cards)
in addition to returning text for Claude.

Set via tool_registry.execute(name, args, emit=fn) before each call.
"""

_emit_fn = None


def set_emit(fn):
    global _emit_fn
    _emit_fn = fn


def emit_card(card_type: str, data: dict):
    """Send a card to the UI for visual display alongside spoken response."""
    if _emit_fn:
        try:
            _emit_fn("card", {"type": card_type, "data": data})
        except Exception:
            pass


def emit_event(event: str, payload: dict):
    if _emit_fn:
        try:
            _emit_fn(event, payload)
        except Exception:
            pass
